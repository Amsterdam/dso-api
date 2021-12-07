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

from functools import cached_property

from django.db import models
from django.http import Http404, JsonResponse
from django.utils.translation import gettext as _
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from schematools.contrib.django.models import DynamicModel
from schematools.exceptions import SchemaObjectNotFound

from dso_api.dynamic_api import filterset, locking, permissions, serializers
from dso_api.dynamic_api.temporal import TemporalTableQuery
from rest_framework_dso import fields
from rest_framework_dso.views import DSOViewMixin


def reload_patterns(request):
    """A view that reloads the current patterns."""
    from ..urls import router

    new_models = router.reload()

    return JsonResponse(
        {
            "models": [
                {
                    "schema": model._meta.app_label,
                    "table": model._meta.model_name,
                    "url": request.build_absolute_uri(url),
                }
                for model, url in new_models.items()
            ]
        }
    )


class DynamicApiViewSet(locking.ReadLockMixin, DSOViewMixin, viewsets.ReadOnlyModelViewSet):
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

    # Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    # The 'bronhouder' of the associated dataset
    authorization_grantor: str = None

    _NON_FILTER_PARAMS = {
        # Allowed request parameters.
        # Except for "page", all the non-underscore-prefixed parameters
        # are for backward compatibility.
        "_count",
        "_expand",
        "_expandScope",
        "_fields",
        "fields",
        "_format",
        "format",
        "_pageSize",
        "page_size",
        "page",
        "_sort",
        "sorteer",
    }

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        table_schema = self.model.table_schema()
        try:
            permissions.validate_request(request, table_schema, self._NON_FILTER_PARAMS)
        except SchemaObjectNotFound as e:
            raise ValidationError(str(e)) from e
        self.temporal = TemporalTableQuery(request, table_schema)

    @cached_property
    def lookup_field(self):
        """Overwritten from GenericAPIView to filter on temporal identifier instead."""
        if self.temporal.is_versioned:
            # Take the first field as grouper from ["identificatie", "volgnummer"]
            return self.model.table_schema().identifier[0]
        else:
            return "pk"

    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        # Apply the ?geldigOp=... filters, unless ?volgnummer=.. is requested.
        # The version_value is checked for here, as the TemporalTableQuery can be
        # checked for a sub object too.
        if self.temporal and not self.temporal.version_value:
            queryset = self.temporal.filter_queryset(queryset)
        return queryset

    def get_object(self) -> DynamicModel:
        """An improved version of GenericAPIView.get_object() that supports temporal objects."""
        if not self.temporal:
            return super().get_object()

        # Despite being a detail view, still allow filters (e.g. ?volgnummer=...)
        queryset = self.filter_queryset(self.get_queryset())

        pk = self.kwargs[self.lookup_url_kwarg]
        if self.lookup_field != "pk":
            # Allow fallback to old full id search (note this may need ?geldigOp=* to work)
            queryset = queryset.filter(models.Q(**{self.lookup_field: pk}) | models.Q(pk=pk))
        else:
            queryset = queryset.filter(pk=pk)

        # Only retrieve the correct temporal object, unless filters change this
        obj = queryset.order_by().first()  # reverse ordering already applied
        if obj is None:
            raise Http404(
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


def _get_viewset_api_docs(model: type[DynamicModel]) -> str:
    """Generate the API documentation header for the viewset."""
    # NOTE: currently not using model.get_dataset_path() as the docs don't do either.
    description = model.table_schema().description
    docs_path = f"datasets/{model.get_dataset_path()}.html#{model.get_table_id()}"
    return (
        f"{description or ''}\n\nSee the documentation at: "
        f"<https://api.data.amsterdam.nl/v1/docs/{docs_path}>"
    )


def _get_ordering_fields(
    serializer_class: type[serializers.DynamicSerializer],
) -> list[str]:
    """Make sure the ordering doesn't happen on foreign relations.
    This creates an unnecessary join, which can be avoided by sorting on the _id field.
    """
    return [
        name
        for name in serializer_class.Meta.fields
        if name not in {"_links", "schema"}
        and not isinstance(getattr(serializer_class, name, None), fields.EmbeddedField)
    ]


def viewset_factory(model: type[DynamicModel]) -> type[DynamicApiViewSet]:
    """Generate the viewset for a dynamic model.

    This generates a class in-memory, as if the following code was written:

    .. code-block:: python

        class CustomViewSet(DynamicApiViewSet):
            dataset_id = ...
            table_id = ...
            model = ...

            queryset = model.objects.all()
            serializer_class = serializer_factory(model)
            filterset_class = filterset_factory(model)
            authorization_grantor = "OIS"
            ordering_fields = ...

    Internally, the :func:`~dso_api.dynamic_api.serializers.serializer_factory`,
    and :func:`~dso_api.dynamic_api.filterset.filterset_factory` functions are called
    to generate those classes.
    """
    serializer_class = serializers.serializer_factory(model)
    filterset_class = filterset.filterset_factory(model)
    ordering_fields = _get_ordering_fields(serializer_class)

    attrs = {
        "__doc__": _get_viewset_api_docs(model),
        "model": model,
        "queryset": model.objects.all(),  # also for OpenAPI schema parsing.
        "serializer_class": serializer_class,
        "filterset_class": filterset_class,
        "ordering_fields": ordering_fields,
        "dataset_id": model._dataset_schema["id"],
        "table_id": model.table_schema()["id"],
        "authorization_grantor": model.get_dataset_schema().get("authorizationGrantor"),
    }
    return type(f"{model.__name__}ViewSet", (DynamicApiViewSet,), attrs)
