"""The remote views retrieve data from other REST API endpoints.
Currently it mainly performs authorization, data retrieval, and schema validation.
"""
import logging
from typing import Type

from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from schematools.types import DatasetTableSchema

from rest_framework_dso.exceptions import RemoteAPIException
from rest_framework_dso.views import DSOViewMixin

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

    client = None
    serializer_class = None
    pagination_class = None
    table_schema = None

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
        data = self.client.call(request, query_params=request.query_params)
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
        data = self.client.call(request, path=self.kwargs["pk"])
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


def remote_viewset_factory(
    endpoint_url, serializer_class, table_schema: DatasetTableSchema
) -> Type[RemoteViewSet]:
    """Construct the viewset class that handles the remote serializer."""

    return type(
        f"{serializer_class.__name__}Viewset",
        (RemoteViewSet,),
        {
            "__doc__": "Forwarding proxy serializer",
            "client": clients.make_client(endpoint_url, table_schema),
            "serializer_class": serializer_class,
            "dataset_id": table_schema.dataset.id,
            "table_id": table_schema.id,
            "table_schema": table_schema,
        },
    )
