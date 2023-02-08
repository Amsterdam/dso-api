"""The remote views retrieve data from other REST API endpoints.
Currently it mainly performs authorization, data retrieval, and schema validation.
"""
import logging
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import certifi
import orjson
import rest_framework.exceptions
import urllib3
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.views import View
from more_ds.network.url import URL
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import ViewSet
from schematools.naming import toCamelCase
from schematools.types import DatasetTableSchema

from rest_framework_dso.exceptions import RemoteAPIException
from rest_framework_dso.views import DSOViewMixin

from .. import permissions
from . import clients, serializers
from .clients import call

logger = logging.getLogger(__name__)


def _rewrite_links(data, fn: Callable[[str], str], in_links: bool = False):
    """Replace hrefs in _links sections by whatever fn returns for them.

    May modify data destructively.
    """
    if isinstance(data, list):
        for i in range(len(data)):
            data[i] = _rewrite_links(data[i], fn, in_links)
        return data
    elif isinstance(data, dict):
        if in_links and isinstance(href := data.get("href"), str):
            data["href"] = fn(href)
            return data
        return {k: _rewrite_links(v, fn, in_links or k == "_links") for k, v in data.items()}
    else:
        return data


class HaalCentraalBAG(View):
    """View that proxies Haal Centraal BAG.

    This is simple pass-through proxy: we change the url, send the request on,
    then fix up the response so that self/next/prev links point to us instead of HC.
    """

    _BASE_URL = urljoin(settings.DATAPUNT_API_URL, "v1/haalcentraal/bag/")  # XXX use reverse?

    def __init__(self):
        super().__init__()
        self.pool = urllib3.PoolManager()

    def get(self, request: HttpRequest, subpath: str):
        url: str = settings.HAAL_CENTRAAL_BAG_ENDPOINT + subpath
        headers = {"Accept": "application/hal+json"}
        if (apikey := settings.HAAL_CENTRAAL_BAG_API_KEY) is not None:
            headers["X-Api-Key"] = apikey

        logger.info("calling %s", url)
        response = call(self.pool, url, fields=request.GET, headers=headers)
        data = orjson.loads(response.data)
        data = _rewrite_links(data, self._rewrite_href)
        return HttpResponse(orjson.dumps(data), content_type=response.headers.get("Content-Type"))

    def _rewrite_href(self, href: str) -> str:
        if href.startswith(settings.HAAL_CENTRAAL_BAG_ENDPOINT):
            href = self._BASE_URL + href[len(settings.HAAL_CENTRAAL_BAG_ENDPOINT) :]
        return href


class HaalCentraalBRK(View):
    """View that proxies Haal Centraal BRK.

    This is a pass-through proxy like BAG, but with authorization added.
    """

    _BASE_URL = urljoin(settings.DATAPUNT_API_URL, "v1/haalcentraal/brk/")  # XXX use reverse?
    _BASE_URL_BAG = urljoin(settings.DATAPUNT_API_URL, "v1/haalcentraal/bag/")
    _NEEDED_SCOPES = ["BRK/RO", "BRK/RS", "BRK/RSN"]

    def __init__(self):
        super().__init__()
        if ".acceptatie." in urlparse(settings.HAAL_CENTRAAL_BRK_ENDPOINT).netloc:
            self.pool = urllib3.PoolManager()
        else:
            self.pool = urllib3.PoolManager(
                cert_file=settings.HAAL_CENTRAAL_CERTFILE,
                cert_reqs="CERT_REQUIRED",
                key_file=settings.HAAL_CENTRAAL_KEYFILE,
                ca_certs=certifi.where(),
            )

    def get(self, request: HttpRequest, subpath: str):
        access = request.user_scopes.has_all_scopes(*self._NEEDED_SCOPES)
        permissions.log_access(request, access)
        if not access:
            raise PermissionDenied(f"You need scopes {self._NEEDED_SCOPES}")

        url: str = settings.HAAL_CENTRAAL_BRK_ENDPOINT + subpath
        headers = {
            "Accept": "application/hal+json",
            "Accept-Crs": "epsg:28992",
        }
        if (apikey := settings.HAAL_CENTRAAL_API_KEY) is not None:
            headers["X-Api-Key"] = apikey

        logger.info("calling %s", url)  # Log without query parameters, since those are sensitive.
        response = call(self.pool, url, fields=request.GET, headers=headers)
        data = orjson.loads(response.data)
        data = _rewrite_links(data, self._rewrite_href)
        return HttpResponse(orjson.dumps(data), content_type=response.headers.get("Content-Type"))

    def _rewrite_href(self, href: str):
        # Unlike HC BAG, HC BRK produces relative URLs. But it may also produce links to the BAG,
        # which are absolute URLs that point to api.bag.kadaster.nl.
        if href.startswith("/"):
            return self._BASE_URL + href[1:]
        elif href.startswith("https://api.bag.kadaster.nl/esd/huidigebevragingen/v1/"):
            href = href[len("https://api.bag.kadaster.nl/esd/huidigebevragingen/v1/") :]
            return self._BASE_URL_BAG + href


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

    client: clients.RemoteClient = None
    serializer_class = None
    table_schema: Optional[DatasetTableSchema] = None

    # The 'bronhouder' of the associated dataset
    authorization_grantor: str = None

    def get_serializer(self, *args, **kwargs) -> serializers.RemoteSerializer:
        """Instantiate the serializer that validates the remote data."""
        if self.serializer_class is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__}.serializer_class is not set")

        kwargs["context"] = self.get_serializer_context(
            content_crs=kwargs.pop("content_crs", None)
        )
        return self.serializer_class(*args, **kwargs)

    def get_serializer_context(self, content_crs=None):
        """Extra context provided to the serializer class."""
        return {
            "request": self.request,
            "format": self.format_kwarg,
            "view": self,
            "content_crs": content_crs,
        }

    def list(self, request, *args, **kwargs):
        """The GET request for listings"""
        access = request.user_scopes.has_dataset_access(
            self.table_schema.dataset
        ) and request.user_scopes.has_table_access(self.table_schema)
        permissions.log_access(request, access)
        if not access:
            raise rest_framework.exceptions.PermissionDenied()

        # Retrieve the remote JSON data
        response = self.client.call(request, query_params=request.query_params)
        data = response.data
        if "_embedded" in data and isinstance(data["_embedded"], dict):
            # unwrap list response from HAL-JSON / DSO standard
            data = next(iter(data["_embedded"].values())) if data["_embedded"] else []

        # Pass inside serializer so only the allowed fields are returned,
        # and no fields will be added that didn't match the schema
        serializer = self.get_serializer(data=data, many=True, content_crs=response.content_crs)
        self.validate(serializer)

        # Work around the serializer producing the wrong format.
        data = serializer.data

        id_field = self.table_schema.identifier[0]
        schema = data[0]["schema"] if data else None
        url = self.request.build_absolute_uri(self.request.path)

        for row in data:
            del row["schema"]
            ident = row[id_field]

            row["_links"] = {
                "schema": schema,
                "self": {
                    "href": URL(url) / ident,
                    "title": ident,
                },
            }

        data = {
            "_embedded": {
                toCamelCase(self.table_schema.id): data,
            },
            "_links": {
                "self": {
                    "href": url,
                },
            },
        }

        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        """The GET request for detail"""
        access = request.user_scopes.has_dataset_access(
            self.table_schema.dataset
        ) and request.user_scopes.has_table_access(self.table_schema)
        permissions.log_access(request, access)
        if not access:
            raise rest_framework.exceptions.PermissionDenied()

        # Retrieve the remote JSON data
        response = self.client.call(request, path=self.kwargs["pk"])
        serializer = self.get_serializer(data=response.data, content_crs=response.content_crs)

        # Validate data. This also excludes fields which the user doesn't have access to.
        self.validate(serializer)
        serialized_data = serializer.data
        _del_none(serialized_data)

        # Add self url.
        self_link = self.request.build_absolute_uri(self.request.path)
        if "_links" not in serialized_data:
            serialized_data["_links"] = {"self": {"href": self_link}}

        return Response(serialized_data)

    def validate(self, serializer: BaseSerializer):
        if serializer.is_valid():
            return

        # Log a sanitized version of serializer.errors with minimal information about the
        # remote response's contents. errors is supposed to be a map with field names as keys
        # (https://www.django-rest-framework.org/api-guide/serializers/#validation),
        # but in list views, it's a ReturnList of such dicts.
        error_fields = set()
        if isinstance(serializer.errors, dict):
            error_fields = set(serializer.errors.keys())
        else:
            for error in serializer.errors:
                error_fields |= error.keys()

        logger.error("Fields %s in the remote response did not validate", sorted(error_fields))

        raise RemoteAPIException(
            title="Invalid remote data",
            detail="Some fields in the remote's response did not match the schema",
            code="validation_errors",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


def remote_viewset_factory(
    endpoint_url, serializer_class, table_schema: DatasetTableSchema
) -> type[RemoteViewSet]:
    """Construct the viewset class that handles the remote serializer."""

    return type(
        f"{table_schema.python_name}ViewSet",
        (RemoteViewSet,),
        {
            "client": clients.make_client(endpoint_url, table_schema.dataset.id, table_schema.id),
            "serializer_class": serializer_class,
            "dataset_id": table_schema.dataset.id,
            "table_id": table_schema.id,
            "table_schema": table_schema,
            "authorization_grantor": table_schema.dataset.get("authorizationGrantor"),
        },
    )
