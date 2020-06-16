import certifi
import logging
import orjson
import urllib3
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, NotFound, ParseError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from typing import Type, Union
from urllib.parse import urljoin
from urllib3 import HTTPResponse

from dso_api.lib.exceptions import (
    BadGateway,
    GatewayTimeout,
    RemoteAPIException,
    ServiceUnavailable,
)
from . import serializers
from .. import permissions

logger = logging.getLogger(__name__)
http_pool = urllib3.PoolManager(cert_reqs="CERT_REQUIRED", ca_certs=certifi.where())


class RemoteViewSet(ViewSet):
    """Views for a remote serializer."""

    serializer_class = None
    endpoint_url = None

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
            raise ImproperlyConfigured(
                f"{self.__class__.__name__}.serializer_class is not set"
            )

        kwargs["context"] = self.get_serializer_context()
        return self.serializer_class(*args, **kwargs)

    def get_serializer_context(self):
        """Extra context provided to the serializer class."""
        return {"request": self.request, "format": self.format_kwarg, "view": self}

    def list(self, request, *args, **kwargs):
        """The GET request for listings"""
        data = self._call_remote()
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
        self.validate(serializer, data)

        return Response(serializer.data)

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

    def _call_remote(self, url="") -> Union[dict, list]:
        """Make a request to the remote server"""
        if not self.endpoint_url:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__}.endpoint_url is not set"
            )

        if not url:
            url = self.endpoint_url
        else:
            url = urljoin(self.endpoint_url, url)

        # Using urllib directly instead of requests for performance
        logger.debug("Forwarding call to %s", url)
        headers = self.get_headers()
        try:
            response: HTTPResponse = http_pool.request(
                "GET", url, headers=headers, timeout=60, retries=False,
            )
        except (TimeoutError, urllib3.exceptions.TimeoutError) as e:
            logger.debug("Proxy call failed: %s", e)
            raise GatewayTimeout() from e
        except (OSError, urllib3.exceptions.HTTPError) as e:
            # Any remaining socket / SSL error
            logger.debug("Proxy call failed: %s", e)
            raise ServiceUnavailable(str(e)) from e

        if response.status == 200:
            return orjson.loads(response.data)

        return self._raise_http_error(response)

    def _raise_http_error(self, response: HTTPResponse):  # noqa: C901
        """Translate the remote HTTP error to the proper response."""
        content_type = response.headers.get("content-type")
        logger.debug("Proxy call failed: %s", response.reason)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("  Response body: %s", response.data)

        if response.headers.get("content-type", "").startswith("text/html"):
            detail_message = None
        else:
            detail_message = response.data.decode()

        if response.status == 400:
            if response.data == b"Missing required MKS headers":
                raise NotAuthenticated("Internal credentials are missing")
            elif content_type == "application/problem+json":
                raise RemoteAPIException(
                    title=ParseError.default_detail,
                    detail=orjson.loads(response.data),
                    code=ParseError.default_code,
                    status_code=400,
                )
            else:
                raise BadGateway(detail_message)
        elif response.status == 403:
            # Return 403 to client as well
            raise NotAuthenticated(detail_message)
        elif response.status == 404:
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
            raise ServiceUnavailable(detail_message)

    def get_headers(self):
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

        for header in self.headers_passthrough:
            value = self.request.headers.get(header, "")
            if not value:
                continue

            if isinstance(value, str):
                # Based on DRF's get_authorization_header() logic:
                # Work around django test client oddness
                value = value.encode("iso-8859-1")
            headers[header] = value

        return headers


def remote_viewset_factory(endpoint_url, serializer_class) -> Type[RemoteViewSet]:
    """Construct the viewset class that handles the remote serializer."""
    return type(
        f"{serializer_class.__name__}Viewset",
        (RemoteViewSet,),
        {
            "__doc__": "Forwarding proxy serializer",
            "endpoint_url": endpoint_url,
            "serializer_class": serializer_class,
        },
    )
