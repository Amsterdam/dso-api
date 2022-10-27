"""The remote views retrieve data from other REST API endpoints.
Currently it mainly performs authorization, data retrieval, and schema validation.
"""
import logging
from typing import Optional

from django.core.exceptions import ImproperlyConfigured
from more_ds.network.url import URL
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import ViewSet
from schematools.naming import toCamelCase
from schematools.types import DatasetTableSchema

from rest_framework_dso.exceptions import RemoteAPIException
from rest_framework_dso.views import DSOViewMixin

from .. import permissions
from . import clients, serializers

logger = logging.getLogger(__name__)


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
    pagination_class = None
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
            raise PermissionDenied()

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

        # TODO: add pagination:
        # paginator = self.pagination_class()
        # paginator.get_paginated_response(serializer.data)

        # Work around the serializer producing the wrong format.
        # TODO: fix the serializer instead? What we get from the Kadaster remote
        #  looks more what we want than what comes out of the serializer.
        #  Is something wrong with BRP remote output?
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
            raise PermissionDenied()

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


def _get_viewset_api_docs(table_schema: DatasetTableSchema) -> str:
    return table_schema.description or "Forwarding proxy"


def remote_viewset_factory(
    endpoint_url, serializer_class, table_schema: DatasetTableSchema
) -> type[RemoteViewSet]:
    """Construct the viewset class that handles the remote serializer."""

    return type(
        f"{table_schema.python_name}ViewSet",
        (RemoteViewSet,),
        {
            "__doc__": _get_viewset_api_docs(table_schema),
            "client": clients.make_client(endpoint_url, table_schema),
            "serializer_class": serializer_class,
            "dataset_id": table_schema.dataset.id,
            "table_id": table_schema.id,
            "table_schema": table_schema,
            "authorization_grantor": table_schema.dataset.get("authorizationGrantor"),
        },
    )
