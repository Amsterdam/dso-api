"""Clients for remote APIs.

Endpoints are queried with raw urllib3,
to avoid the overhead of the requests library.
"""

import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import certifi
import orjson
import urllib3
from django.core.exceptions import ImproperlyConfigured
from more_ds.network.url import URL
from rest_framework.exceptions import APIException, NotFound, ParseError, PermissionDenied
from rest_framework.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from urllib3 import HTTPResponse

from rest_framework_dso.crs import CRS
from rest_framework_dso.exceptions import (
    BadGateway,
    GatewayTimeout,
    RemoteAPIException,
    ServiceUnavailable,
)

logger = logging.getLogger(__name__)

_http_pool_generic = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())


@dataclass(frozen=True)
class RemoteResponse:
    """The response from the remote system"""

    content_crs: CRS | None
    data: list | dict


def call(pool: urllib3.PoolManager, url: str, **kwargs) -> HTTPResponse:
    """Make an HTTP GET call. kwargs are passed to pool.request."""

    host = urlparse(url).netloc
    t0 = time.perf_counter_ns()
    try:
        # Using urllib directly instead of requests for performance
        response: HTTPResponse = pool.request(
            "GET",
            url,
            timeout=60,
            retries=False,
            **kwargs,
        )
    except (TimeoutError, urllib3.exceptions.TimeoutError) as e:
        # Socket timeout
        logger.error("Proxy call to %s failed, timeout from remote server: %s", host, e)
        raise GatewayTimeout() from e
    except (OSError, urllib3.exceptions.HTTPError) as e:
        # Socket connect / SSL error (HTTPError is the base class for errors)
        logger.error("Proxy call to %s failed, error when connecting to server: %s", host, e)
        raise ServiceUnavailable(str(e)) from e

    # Log response and timing results
    level = logging.ERROR if response.status >= 400 else logging.INFO
    logger.log(
        level,
        "Proxy call to %s, status %s: %s, took: %.3fs",
        host,
        response.status,
        response.reason,
        (time.perf_counter_ns() - t0) * 1e-9,
    )

    if response.status >= 200 and response.status < 300:
        return response

    # We got an error.
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("  Response body: %s", response.data)

    raise _get_http_error(response)


def _get_http_error(response: HTTPResponse) -> APIException:
    # Translate the remote HTTP error to the proper response.
    #
    # This translates some errors into a 502 "Bad Gateway" or 503 "Gateway Timeout"
    # error to reflect the fact that this API is calling another service as backend.

    # Consider the actual JSON response here,
    # unless the request hit the completely wrong page (it got an HTML page).
    content_type = response.headers.get("content-type", "")
    detail_message = response.data.decode() if not content_type.startswith("text/html") else None

    if response.status == 400:  # "bad request"
        if content_type == "application/problem+json":
            # Translate proper "Bad Request" to REST response
            return RemoteAPIException(
                title=ParseError.default_detail,
                detail=orjson.loads(response.data),
                code=ParseError.default_code,
                status_code=400,
            )
        else:
            return BadGateway(detail_message)
    elif response.status in (HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN):
        # We translate 401 to 403 because 401 MUST have a WWW-Authenticate
        # header in the response and we can't easily set that from here.
        # Also, RFC 7235 says we MUST NOT change such a header,
        # which presumably includes making one up.
        return RemoteAPIException(
            title=PermissionDenied.default_detail,
            detail=f"{response.status} from remote: {response.data!r}",
            status_code=HTTP_403_FORBIDDEN,
            code=PermissionDenied.default_code,
        )
    elif response.status == 404:  # "not found"
        # Return 404 to client (in DRF format)
        if content_type == "application/problem+json":
            # Forward the problem-json details, but still in a 404:
            return RemoteAPIException(
                title=NotFound.default_detail,
                detail=orjson.loads(response.data),
                status_code=404,
                code=NotFound.default_code,
            )
        return NotFound(detail_message)
    else:
        # Unexpected response, call it a "Bad Gateway"
        logger.error(
            "Proxy call failed, unexpected status code from endpoint: %s %s",
            response.status,
            detail_message,
        )
        return BadGateway(
            detail_message or f"Unexpected HTTP {response.status} from internal endpoint"
        )


class RemoteClient:
    """Generic remote API client.

    This class can be used directly, or as the base class for custom classes
    that perform API-specific logic.
    """

    _endpoint_url: URL
    _table_id: str

    def __init__(self, endpoint_url: str, table_id: str):
        self._endpoint_url = endpoint_url
        self._table_id = table_id

    def call(self, request, path="", query_params=None):
        raise NotImplementedError()

    def _parse_response(self, response: HTTPResponse) -> RemoteResponse:
        """Parse the retrieved HTTP response"""
        content_crs = response.headers.get("Content-Crs")
        return RemoteResponse(
            content_crs=CRS.from_string(content_crs) if content_crs else None,
            data=orjson.loads(response.data),
        )

    def _get_http_pool(self) -> urllib3.PoolManager:
        """Returns a PoolManager for making HTTP requests."""
        return _http_pool_generic

    def _make_url(self, path: str, query_params: dict) -> URL:
        if not self._endpoint_url:
            raise ImproperlyConfigured(f"{self.__class__.__name__}._endpoint_url is not set")

        url = self._endpoint_url if not path else URL(self._endpoint_url) / path

        url = URL(url.replace("{table_id}", self._table_id))
        return url // query_params


class BRPClient(RemoteClient):
    """RemoteClient for brp. Passes Authorization headers through to the remote."""

    def call(self, request, path="", query_params=None) -> RemoteResponse:
        """Make a request to the remote server based on the client's request."""
        url = self._make_url(path, query_params or {})
        response = call(self._get_http_pool(), url, headers=self._get_headers(request))
        if 300 <= response.status <= 399 and (
            "/oauth/authorize" in response.headers.get("Location", "")
        ):
            raise PermissionDenied("Invalid token")
        return self._parse_response(response)

    def _get_headers(self, request):
        headers = {
            "Accept": "application/json",
            "X-Fowarded-For": self._forwarded_for(request),
        }

        # We check if we already have an X-Correlation-ID header
        x_correlation_id = request.headers.get("X-Correlation-ID")
        if not x_correlation_id:
            # Otherwise we set it to a part of the X-Unique-ID header
            # The X-Correlation-ID cannot be longer then 40 characters because MKS suite
            # cannot handle this. Therefore  we use only part of it.
            # The X-Unique-ID is defined in Openstack with :
            # [client_ip]:[client_port]_[bind_ip]:[bind_port]_[timestamp]_[request_counter]:[pid]
            # But bind_ip and bind_port are always the same. So we can remove them
            x_unique_id = request.headers.get("X-Unique-ID")
            if x_unique_id:
                x_correlation_id = x_unique_id[:14] + x_unique_id[28:]
        if x_correlation_id:
            # And if defined pass on to the destination
            headers["X-Correlation-ID"] = x_correlation_id.encode("iso-8859-1")

        auth = request.headers.get("Authorization", "")
        if auth:
            if isinstance(auth, str):
                # Based on DRF's get_authorization_header() logic:
                # Work around django test client oddness
                auth = auth.encode("iso-8859-1")
            headers["Authorization"] = auth

        return headers

    def _forwarded_for(self, request) -> bytes:
        client_ip = request.META["REMOTE_ADDR"]
        if isinstance(client_ip, str):
            client_ip = client_ip.encode("ascii")
        forw_for = request.headers.get("X-Forwarded-For", b"")
        if forw_for:
            if isinstance(forw_for, str):
                forw_for = forw_for.encode("ascii")
            # XXX X-Forwarded-For usually takes a comma-separated list.
            # I'm not sure why we have a space-separated list here, but we've always had it.
            forw_for = b"%b %b" % (forw_for, client_ip)
        else:
            forw_for = client_ip

        return forw_for


def make_client(endpoint_url: str, dataset_id: str, table_id: str) -> RemoteClient:
    """Construct client for a remote API."""

    if dataset_id not in ("brp", "brp_test"):
        raise ValueError(f"unknown remote {dataset_id!r}")
    return BRPClient(endpoint_url, table_id)
