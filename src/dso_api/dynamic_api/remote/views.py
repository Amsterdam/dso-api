"""The remote views retrieve data from other REST API endpoints.
Currently it mainly performs authorization, data retrieval, and schema validation.
The endpoint is queried with raw urllib3 logic, to avoid the overhead of the requests library.
"""
import logging
from typing import Type, Union
from urllib.parse import urlencode, urljoin, urlparse

import certifi
import orjson
import urllib3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, NotFound, ParseError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from urllib3 import HTTPResponse

from dso_api.dynamic_api import permissions
from rest_framework_dso.exceptions import (
    BadGateway,
    GatewayTimeout,
    RemoteAPIException,
    ServiceUnavailable,
)
from rest_framework_dso.views import DSOViewMixin

from . import serializers

logger = logging.getLogger(__name__)


_http_pool_generic = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())

_http_pool_kadaster = None


def _get_http_pool(dataset_id, endpoint_url):
    if dataset_id == "hcbrk" and ".acceptatie." not in urlparse(endpoint_url).netloc:
        global _http_pool_kadaster
        if _http_pool_kadaster is None:
            _http_pool_kadaster = urllib3.PoolManager(
                cert_file=settings.HAAL_CENTRAAL_CERTFILE,
                cert_reqs="CERT_REQUIRED",
                key_file=settings.HAAL_CENTRAAL_KEYFILE,
                ca_certs=certifi.where(),
            )
        return _http_pool_kadaster

    else:
        return _http_pool_generic


def _del_none(d):
    """
    Delete keys with the value ``None`` in a dictionary, recursively.

    This alters the input so you may wish to ``copy`` the dict first.
    """
    for key, value in list(d.items()):
        if value is None:
            del d[key]
        elif isinstance(value, dict):
            _del_none(value)


class RemoteViewSet(DSOViewMixin, ViewSet):
    """Views for a remote serializer.

    This viewset retrieves the data from a remote endpoint.
    """

    serializer_class = None
    pagination_class = None
    endpoint_url = None
    dataset_id = None
    table_id = None
    table_schema = None

    default_headers = {
        "Accept": "application/json; charset=utf-8",
        # "MKS_APPLICATIE": "...",
        # "MKS_GEBRUIKER": "...",
    }
    headers_passthrough = ("Authorization",)

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    def get_serializer(self, *args, **kwargs) -> serializers.RemoteSerializer:
        """Instantiate the serializer that validates the remote data."""
        if self.serializer_class is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__}.serializer_class is not set")

        kwargs["context"] = self.get_serializer_context()
        return self.serializer_class(*args, **kwargs)

    def get_serializer_context(self):
        """Extra context provided to the serializer class."""
        return {"request": self.request, "format": self.format_kwarg, "view": self}

    def list(self, request, *args, **kwargs):
        """The GET request for listings"""
        data = self._call_remote(query_params=request.query_params)
        if "_embedded" in data and isinstance(data["_embedded"], dict):
            data = next(iter(data["_embedded"].values())) if data["_embedded"] else []
        serializer = self.get_serializer(data=data, many=True)
        self.validate(serializer, data)

        # TODO: add pagination:
        # paginator = self.pagination_class()
        # paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """The GET request for detail"""
        data = self._call_remote(url=self.kwargs["pk"])
        serializer = self.get_serializer(data=data)
        # Validate data. Throw exception if not valid
        self.validate(serializer, data)
        serialized_data = serializer.data
        _del_none(serialized_data)
        # Add self url.
        self_link = self.request.build_absolute_uri(self.request.path)
        if "_links" not in serialized_data:
            serialized_data["_links"] = {"self": {"href": self_link}}
        return Response(serialized_data)

    def validate(self, serializer, raw_data):
        if not serializer.is_valid():
            raise RemoteAPIException(
                title="Invalid remote data",
                detail={
                    "detail": "These schema fields did not validate:",
                    "x-validation-errors": serializer.errors,
                    "x-raw-response": raw_data,
                },
                code="validation_errors",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

    def _call_remote(self, url="", query_params={}) -> Union[dict, list]:  # noqa: C901
        """Make a request to the remote server"""
        if not self.endpoint_url:
            raise ImproperlyConfigured(f"{self.__class__.__name__}.endpoint_url is not set")

        if not url:
            url = self.endpoint_url
        else:
            url = urljoin(self.endpoint_url, url)

        if query_params:
            url = urljoin(self.endpoint_url, "?" + urlencode(query_params))

        url = url.replace("{table_id}", self.table_id)

        # Using urllib directly instead of requests for performance
        logger.debug("Forwarding call to %s", url)
        headers = self.get_headers()

        http_pool = _get_http_pool(self.dataset_id, self.endpoint_url)

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
            logger.error("Proxy call failed, timeout from remote server: %s", e)
            raise GatewayTimeout() from e
        except (OSError, urllib3.exceptions.HTTPError) as e:
            # Socket connect / SSL error (HTTPError is the base class for errors)
            logger.error("Proxy call failed, error when connecting to server: %s", e)
            raise ServiceUnavailable(str(e)) from e

        if response.status == 200:
            return orjson.loads(response.data)

        return self._raise_http_error(response)

    def _raise_http_error(self, response: HTTPResponse):  # noqa: C901
        """Translate the remote HTTP error to the proper response.

        This translates some errors into a 502 "Bad Gateway" or 503 "Gateway Timeout"
        error to reflect the fact that this API is calling another service as backend.
        """
        # Generic logging
        level = logging.ERROR if response.status >= 500 else logging.DEBUG
        logger.log(level, "Proxy call failed, status %s: %s", response.status, response.reason)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("  Response body: %s", response.data)

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            # HTML error, probably hit the completely wrong page.
            detail_message = None
        else:
            # Consider the actual JSON response to be relevant here.
            detail_message = response.data.decode()

        if 300 <= response.status <= 399 and (
            "/oauth/authorize" in response.headers.get("Location", "")
        ):
            raise NotAuthenticated("Invalid token")
        elif response.status == 400:  # "bad request"
            if response.data == b"Missing required MKS headers":
                # Didn't pass the MKS_APPLICATIE / MKS_GEBRUIKER headers.
                # Shouldn't occur anymore since it's JWT-token based now.
                raise NotAuthenticated("Internal credentials are missing")
            elif content_type == "application/problem+json":
                # Translate proper "Bad Request" to REST response
                raise RemoteAPIException(
                    title=ParseError.default_detail,
                    detail=orjson.loads(response.data),
                    code=ParseError.default_code,
                    status_code=400,
                )
            else:
                raise BadGateway(detail_message)
        elif response.status == 403:  # "forbidden"
            # Return 403 to client as well
            raise NotAuthenticated(detail_message)
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

    def get_headers(self):  # noqa: C901
        """Collect the headers to submit to the remote service."""
        client_ip = self.request.META["REMOTE_ADDR"]
        if isinstance(client_ip, str):
            client_ip = client_ip.encode("iso-8859-1")
        forward = self.request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forward:
            if isinstance(forward, str):
                forward = forward.encode("iso-8859-1")
            forward = b"%b %b" % (forward, client_ip)
        else:
            forward = client_ip

        headers = {
            **self.default_headers,
            "X-Forwarded-For": forward,
        }

        # We check if we already have a X-Correlation-ID header
        x_correlation_id = self.request.META.get("HTTP_X_CORRELATION_ID")
        if not x_correlation_id:
            # Otherwise we set it to a part of the X-Unique-ID header
            # The X-Correlation-ID cannot be longer then 40 characters because MKS suite
            # cannot handle this. Therefore  we use only part of it.
            # The X-Unique_ID is defined in Openstack with :
            # [client_ip]:[client_port]_[bind_ip]:[bind_port]_[timestamp]_[request_counter]:[pid]
            # But bind_ip and bind_port are always the same. So we can remove them
            x_unique_id = self.request.META.get("HTTP_X_UNIQUE_ID")
            if x_unique_id:
                x_correlation_id = x_unique_id[:14] + x_unique_id[28:]
        if x_correlation_id:
            # And if defined pass on to the destination
            headers["X-Correlation-ID"] = x_correlation_id.encode("iso-8859-1")

        for header in self.headers_passthrough:
            value = self.request.headers.get(header, "")
            if not value:
                continue

            if isinstance(value, str):
                # Based on DRF's get_authorization_header() logic:
                # Work around django test client oddness
                value = value.encode("iso-8859-1")
            headers[header] = value

        if "kadaster.nl" in self.endpoint_url:
            headers["X-Api-Key"] = settings.HAAL_CENTRAAL_API_KEY
            headers["accept"] = "application/hal+json"
            # Currently for kadaster HaalCentraal only RD (epsg:28992) is supported
            headers["Accept-Crs"] = "epsg:28992"

        return headers


def remote_viewset_factory(
    endpoint_url, serializer_class, dataset_id, table_id, table_schema
) -> Type[RemoteViewSet]:
    """Construct the viewset class that handles the remote serializer."""
    return type(
        f"{serializer_class.__name__}Viewset",
        (RemoteViewSet,),
        {
            "__doc__": "Forwarding proxy serializer",
            "endpoint_url": endpoint_url,
            "serializer_class": serializer_class,
            "dataset_id": dataset_id,
            "table_id": table_id,
            "table_schema": table_schema,
        },
    )
