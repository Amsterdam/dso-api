"""The REST API views are based on Django-Rest-Framework.

The viewsets handle the main API logic of the server.
The relevant subclasses are dynamically generated from Amsterdam Schema files,
just like the rest of the objects (such as serializers, filtersets and models).

To maintain readable code for the dynamic viewsets, all logic can be found in a normal Python
class (namely the :class:`~dso_api.dynamic_api.views.DynamicApiViewSet` base class).
The :func:`~dso_api.dynamic_api.views.viewset_factory` function then generates a subclass
for the specific model/endpoint. The same two-step logic can be found in the serializer
and model layer of this application.
"""

from __future__ import annotations

import logging
from functools import cached_property

from django.db import models
from django.db.utils import ProgrammingError
from django.utils.translation import gettext as _
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from schematools.contrib.django.models import DynamicModel

from dso_api.dynamic_api import filters, permissions, serializers
from dso_api.dynamic_api.constants import DEFAULT
from dso_api.dynamic_api.temporal import TemporalTableQuery
from dso_api.dynamic_api.utils import limit_queryset_for_scopes
from rest_framework_dso.views import DSOViewMixin

logger = logging.getLogger(__name__)


class DynamicApiViewSet(DSOViewMixin, viewsets.ReadOnlyModelViewSet):
    """Viewset for an API, that is DSO-compatible and dynamically generated.
    Each dynamically generated model in this server will receive a viewset.

    Most of the DSO logic is implemented in the base class;
    :class:`~rest_framework_dso.views.DSOViewMixin`.
    """

    #: The dataset ID is filled in by the factory
    dataset_id = None
    #: The table ID is filled in by the factory
    table_id = None
    #: The model is filled in by the factory
    model: type[DynamicModel] = None

    # Make sure composed keys like (112740.024|487843.078) are allowed.
    # The DefaultRouter won't allow '.' in URLs because it's used as format-type.
    lookup_value_regex = r"[^/]+"
    lookup_url_kwarg = "pk"

    # Use our custom Amsterdam-schema backend for query filtering
    filter_backends = [
        filters.DynamicFilterBackend,
        filters.DynamicOrderingFilter,
    ]

    # Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    # The 'bronhouder' of the associated dataset
    authorization_grantor: str = None

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except ProgrammingError as e:
            self._handle_db_error(e)
            raise

    def retrieve(self, request, *args, **kwargs):
        try:
            return super().retrieve(request, *args, **kwargs)
        except ProgrammingError as e:
            self._handle_db_error(e)
            raise

    def _handle_db_error(self, e: ProgrammingError) -> None:
        """Make sure database permission errors are gratefully handled.
        This is a common source of 500 error issues,
        and giving a better response to the user helps.
        """
        if str(e).startswith("permission denied for "):
            logger.exception("Database role has no access (while application allowed): %s", e)
            raise PermissionDenied(
                "Database role has no access to the given tables"
                " (schema permissions were satisfied).",
                code="db_permission_denied",
            ) from e

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        table_schema = self.model.table_schema()

        if request.method == "OPTIONS":
            # No permission checks for metadata inquiry
            self.temporal = None
        else:
            self.temporal = TemporalTableQuery.from_request(request, table_schema)

    @cached_property
    def lookup_field(self):
        """Overwritten from GenericAPIView to filter on temporal identifier instead."""
        if self.temporal.is_versioned:
            # Take the first field as grouper from ["identificatie", "volgnummer"]
            return self.model.table_schema().identifier_fields[0].python_name
        else:
            return "pk"

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        queryset = limit_queryset_for_scopes(
            self.request.user_scopes,
            self.model.table_schema().get_fields(include_subfields=True),
            queryset,
        )

        # Apply the ?geldigOp=... filters, unless ?volgnummer=.. is requested.
        # The version_value is checked for here, as the TemporalTableQuery can be
        # checked for a sub object too.
        if self.temporal and not self.temporal.version_value:
            queryset = self.temporal.filter_queryset(queryset)
        return queryset

    def get_object(self) -> DynamicModel:
        """An improved version of GenericAPIView.get_object() that supports temporal objects.

        Initially there was a shortcut in this method. For non-temporal objects,
        the item was collected using a `get_object()` call. However, database access
        has changed, so this approach resulted in a permission error for fields that
        were not allowed according to the scopes of the requesting user.
        """

        # Despite being a detail view, still allow filters (e.g. ?volgnummer=...)
        queryset = self.filter_queryset(self.get_queryset())

        pk = self.kwargs[self.lookup_url_kwarg]
        if self.lookup_field != "pk":
            # Allow fallback to old full id search (note this may need ?geldigOp=* to work)
            queryset = queryset.filter(models.Q(**{self.lookup_field: pk}) | models.Q(pk=pk))
        else:
            try:
                queryset = queryset.filter(pk=pk)
            except ValueError as err:
                raise NotFound(
                    _("No %(verbose_name)s found matching the query")
                    % {"verbose_name": queryset.model._meta.verbose_name}
                ) from err

        # Only retrieve the correct temporal object, unless filters change this
        obj = queryset.order_by().first()  # reverse ordering already applied
        if obj is None:
            raise NotFound(
                _("No %(verbose_name)s found matching the query")
                % {"verbose_name": queryset.model._meta.verbose_name}
            )

        # Same logic as the super method; GenericAPIView.get_object():
        self.check_object_permissions(self.request, obj)
        return obj

    @property
    def paginator(self):
        """The paginator is disabled when a output format supports unlimited sizes."""
        if (
            self.request.accepted_renderer.unlimited_page_size
            and self.pagination_class.page_size_query_param not in self.request.GET
        ):
            # Avoid expensive COUNT(*) for CSV and GeoJSON formats,
            # return all pages by default, unless an explicit page size is requested.
            return None

        return super().paginator


def _get_viewset_api_docs(model: type[DynamicModel], version: str) -> str:
    """Generate the API documentation header for the viewset."""
    description = model.table_schema().description
    suffix = "" if version == DEFAULT else f"@{version}"
    docs_path = f"datasets/{model.get_dataset_path()}{suffix}.html#{model.get_table_id()}"

    return (
        f"{description or ''}\n\nSee the documentation at: "
        f"<https://api.data.amsterdam.nl/v1/docs/{docs_path}>"
    )


def viewset_factory(model: type[DynamicModel], version: str) -> type[DynamicApiViewSet]:
    """Generate the viewset for a dynamic model.

    This generates a class in-memory, as if the following code was written:

    .. code-block:: python

        class CustomViewSet(DynamicApiViewSet):
            dataset_id = ...
            table_id = ...
            model = ...

            queryset = model.objects.all()
            serializer_class = serializer_factory(model, version)
            filterset_class = filterset_factory(model)
            authorization_grantor = "OIS"
            ordering_fields = ...

    Internally, the :func:`~dso_api.dynamic_api.serializers.serializer_factory`,
    function is called to generate those classes.
    """
    serializer_class = serializers.serializer_factory(model, version)
    table_schema = model.table_schema()

    attrs = {
        "__doc__": _get_viewset_api_docs(model, version),
        "model": model,
        "queryset": model.objects.all(),  # also for OpenAPI schema parsing.
        "serializer_class": serializer_class,
        "dataset_id": model._dataset_schema["id"],
        "table_id": model.table_schema()["id"],
        "authorization_grantor": model.get_dataset_schema().get("authorizationGrantor"),
    }
    return type(f"{table_schema.python_name}ViewSet", (DynamicApiViewSet,), attrs)
