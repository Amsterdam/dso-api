"""Clients for remote APIs.

Endpoints are queried with raw urllib3,
to avoid the overhead of the requests library.
"""

import logging
import threading
from typing import Type, Union
from urllib.parse import urlparse

import certifi
import orjson
import urllib3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from more_ds.network.url import URL
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from schematools.types import DatasetTableSchema
from urllib3 import HTTPResponse

from rest_framework_dso.exceptions import (
    BadGateway,
    GatewayTimeout,
    RemoteAPIException,
    ServiceUnavailable,
)

logger = logging.getLogger(__name__)

_http_pool_generic = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())


class RemoteClient:
    """Generic remote API client.

    This class can be used directly, or as the base class for custom classes
    that perform API-specific logic.
    """

    def __init__(self, endpoint_url: str, table_schema: DatasetTableSchema):
        self._endpoint_url = endpoint_url
        self._table_schema = table_schema

    def call(self, request, path="", query_params={}) -> Union[dict, list]:  # noqa: C901
        """Make a request to the remote server based on the client's request."""
        url = self._make_url(path, query_params)

        # Using urllib directly instead of requests for performance
        headers = self._get_headers(request)

        http_pool = self._get_http_pool()

        try:
            response: HTTPResponse = http_pool.request(
                "GET",
                url,
                headers=headers,
                timeout=60,
                retries=False,
            )
        except (TimeoutError, urllib3.exceptions.TimeoutError) as e:
            # Socket timeout
            logger.error("Proxy call to %s failed, timeout from remote server: %s", url, e)
            raise GatewayTimeout() from e
        except (OSError, urllib3.exceptions.HTTPError) as e:
            # Socket connect / SSL error (HTTPError is the base class for errors)
            logger.error("Proxy call to %s failed, error when connecting to server: %s", url, e)
            raise ServiceUnavailable(str(e)) from e

        level = logging.ERROR if response.status >= 400 else logging.INFO
        logger.log(level, "Proxy call to %s, status %s: %s", url, response.status, response.reason)

        if response.status == 200:
            return orjson.loads(response.data)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("  Response body: %s", response.data)

        self._raise_http_error(response)
        raise Exception("_raise_http_error should have raised an exception")

    def _get_headers(self, request):  # noqa: C901
        """Collect the headers to submit to the remote service.

        Subclasses may override this method.
        """
        client_ip = request.META["REMOTE_ADDR"]
        if isinstance(client_ip, str):
            client_ip = client_ip.encode("iso-8859-1")
        forward = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forward:
            if isinstance(forward, str):
                forward = forward.encode("iso-8859-1")
            forward = b"%b %b" % (forward, client_ip)
        else:
            forward = client_ip

        headers = {
            "Accept": "application/json",
            "X-Forwarded-For": forward,
        }

        # We check if we already have a X-Correlation-ID header
        x_correlation_id = request.META.get("HTTP_X_CORRELATION_ID")
        if not x_correlation_id:
            # Otherwise we set it to a part of the X-Unique-ID header
            # The X-Correlation-ID cannot be longer then 40 characters because MKS suite
            # cannot handle this. Therefore  we use only part of it.
            # The X-Unique_ID is defined in Openstack with :
            # [client_ip]:[client_port]_[bind_ip]:[bind_port]_[timestamp]_[request_counter]:[pid]
            # But bind_ip and bind_port are always the same. So we can remove them
            x_unique_id = request.META.get("HTTP_X_UNIQUE_ID")
            if x_unique_id:
                x_correlation_id = x_unique_id[:14] + x_unique_id[28:]
        if x_correlation_id:
            # And if defined pass on to the destination
            headers["X-Correlation-ID"] = x_correlation_id.encode("iso-8859-1")

        return headers

    def _get_http_pool(self) -> urllib3.PoolManager:
        """Returns a PoolManager for making HTTP requests."""
        return _http_pool_generic

    def _make_url(self, path: str, query_params: dict) -> str:
        if not self._endpoint_url:
            raise ImproperlyConfigured(f"{self.__class__.__name__}._endpoint_url is not set")

        if not path:
            url = self._endpoint_url
        else:
            url = URL(self._endpoint_url) / path

        url = URL(url.replace("{table_id}", self._table_schema.id))
        return url // query_params

    def _raise_http_error(self, response: HTTPResponse) -> None:
        """Translate the remote HTTP error to the proper response.

        This translates some errors into a 502 "Bad Gateway" or 503 "Gateway Timeout"
        error to reflect the fact that this API is calling another service as backend.
        """

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            # HTML error, probably hit the completely wrong page.
            detail_message = None
        else:
            # Consider the actual JSON response to be relevant here.
            detail_message = response.data.decode()

        if response.status == 400:  # "bad request"
            if content_type == "application/problem+json":
                # Translate proper "Bad Request" to REST response
                raise RemoteAPIException(
                    title=ParseError.default_detail,
                    detail=orjson.loads(response.data),
                    code=ParseError.default_code,
                    status_code=400,
                )
            else:
                raise BadGateway(detail_message)
        elif response.status in (HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN):
            # We translate 401 to 403 because 401 MUST have a WWW-Authenticate
            # header in the response and we can't easily set that from here.
            # Also, RFC 7235 says we MUST NOT change such a header,
            # which presumably includes making one up.
            raise RemoteAPIException(
                title=PermissionDenied.default_detail,
                detail=f"{response.status} from remote: {response.data!r}",
                status_code=HTTP_403_FORBIDDEN,
                code=PermissionDenied.default_code,
            )
        elif response.status == 404:  # "not found"
            # Return 404 to client (in DRF format)
            if content_type == "application/problem+json":
                # Forward the problem-json details, but still in a 404:
                raise RemoteAPIException(
                    title=NotFound.default_detail,
                    detail=orjson.loads(response.data),
                    status_code=404,
                    code=NotFound.default_code,
                )
            raise NotFound(detail_message)
        else:
            # Unexpected response, call it a "Bad Gateway"
            logger.error(
                "Proxy call failed, unexpected status code from endpoint: %s %s",
                response.status,
                detail_message,
            )
            raise BadGateway(
                detail_message or f"Unexpected HTTP {response.status} from internal endpoint"
            )


class AuthForwardingClient(RemoteClient):
    """RemoteClient that passes Authorization headers through to the remote."""

    def _get_headers(self, request):
        headers = super()._get_headers(request)

        auth = request.headers.get("Authorization", "")
        if auth:
            if isinstance(auth, str):
                # Based on DRF's get_authorization_header() logic:
                # Work around django test client oddness
                auth = auth.encode("iso-8859-1")
            headers["Authorization"] = auth

        return headers

    def _raise_http_error(self, response: HTTPResponse) -> None:
        super()._raise_http_error(response)

        if 300 <= response.status <= 399 and (
            "/oauth/authorize" in response.headers.get("Location", "")
        ):
            raise PermissionDenied("Invalid token")


class HCBRKClient(RemoteClient):
    """Client for HaalCentraal Basisregistratie Kadaster (HCBRK)."""

    # Lazily initialized shared HTTP pool.
    __http_pool = None
    __http_pool_lock = threading.Lock()

    def _get_headers(self, request):
        headers = super()._get_headers(request)

        headers["X-Api-Key"] = settings.HAAL_CENTRAAL_API_KEY
        headers["accept"] = "application/hal+json"
        # Currently for kadaster HaalCentraal only RD (epsg:28992) is supported
        headers["Accept-Crs"] = "epsg:28992"

        return headers

    def _get_http_pool(self) -> urllib3.PoolManager:
        if ".acceptatie." in urlparse(self._endpoint_url).netloc:
            return _http_pool_generic

        with self.__http_pool_lock:
            if self.__http_pool is None:
                self.__http_pool = urllib3.PoolManager(
                    cert_file=settings.HAAL_CENTRAAL_CERTFILE,
                    cert_reqs="CERT_REQUIRED",
                    key_file=settings.HAAL_CENTRAAL_KEYFILE,
                    ca_certs=certifi.where(),
                )
            return self.__http_pool


def make_client(endpoint_url: str, table_schema: DatasetTableSchema) -> RemoteClient:
    """Construct client for a remote API."""

    client_class: Type[RemoteClient] = AuthForwardingClient
    if table_schema.dataset.id == "haalcentraalbrk":
        client_class = HCBRKClient

    return client_class(endpoint_url, table_schema)
