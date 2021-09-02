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

from typing import Iterable, List, Type

from django.db import models
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from more_itertools import first
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset, DynamicModel

from dso_api.dynamic_api import filterset, locking, permissions, serializers
from dso_api.dynamic_api.datasets import get_active_datasets
from rest_framework_dso import fields
from rest_framework_dso.renderers import BrowsableAPIRenderer, HALJSONRenderer
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


class TemporalRetrieveModelMixin:
    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.versioned and self.model.is_temporal():
            if self.request.table_temporal_slice is not None:
                temporal_value = self.request.table_temporal_slice["value"]
                start_field, end_field = self.request.table_temporal_slice["fields"]
                queryset = queryset.filter(**{f"{start_field}__lte": temporal_value}).filter(
                    models.Q(**{f"{end_field}__gte": temporal_value})
                    | models.Q(**{f"{end_field}__isnull": True})
                )

        return queryset

    def get_object(self, queryset=None):
        """
        Do some black magic, find things in DB's garbage bags.
        """
        if queryset is None:
            queryset = self.get_queryset()

        if not self.request.versioned or not self.model.is_temporal():
            return super().get_object()

        table_schema = self.model.table_schema()
        pk = self.kwargs.get("pk")
        pk_field = first(table_schema.identifier)
        if pk_field != "pk":
            queryset = queryset.filter(
                models.Q(**{pk_field: pk}) | models.Q(pk=pk)
            )  # fallback to full id search.
        else:
            queryset = queryset.filter(pk=pk)
        identifier = table_schema.temporal.identifier

        # Filter queryset using GET parameters, if any.
        for field in queryset.model.table_schema().fields:
            if field.name != pk_field and field.name in self.request.GET:
                queryset = queryset.filter(**{field.name: self.request.GET[field.name]})

        if identifier is None:
            queryset = queryset.order_by(pk_field)
        else:
            queryset = queryset.order_by(identifier)

        obj = queryset.last()
        if obj is None:
            raise Http404(
                _("No %(verbose_name)s found matching the query")
                % {"verbose_name": queryset.model._meta.verbose_name}
            )
        return obj


class DynamicApiViewSet(
    TemporalRetrieveModelMixin,
    locking.ReadLockMixin,
    DSOViewMixin,
    viewsets.ReadOnlyModelViewSet,
):
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
    model: Type[DynamicModel] = None

    # Make sure composed keys like (112740.024|487843.078) are allowed.
    # The DefaultRouter won't allow '.' in URLs because it's used as format-type.
    lookup_value_regex = r"[^/]+"

    # Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

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


def _get_viewset_api_docs(model: Type[DynamicModel]) -> str:
    """Generate the API documentation header for the viewset."""
    # NOTE: currently not using model.get_dataset_path() as the docs don't do either.
    description = model.table_schema().description
    docs_path = f"datasets/{model.get_dataset_path()}.html#{model.get_table_id()}"
    return (
        f"{description or ''}\n\nSee the documentation at: "
        f"<https://api.data.amsterdam.nl/v1/docs/{docs_path}>"
    )


def _get_ordering_fields(
    serializer_class: Type[serializers.DynamicSerializer],
) -> List[str]:
    """Make sure the ordering doesn't happen on foreign relations.
    This creates an unnecessary join, which can be avoided by sorting on the _id field.
    """
    return [
        name
        for name in serializer_class.Meta.fields
        if name not in {"_links", "schema"}
        and not isinstance(getattr(serializer_class, name, None), fields.EmbeddedField)
    ]


def viewset_factory(model: Type[DynamicModel]) -> Type[DynamicApiViewSet]:
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
    }
    return type(f"{model.__name__}ViewSet", (DynamicApiViewSet,), attrs)


class APIIndexView(APIView):
    """An overview of API endpoints for a list of Datasets,
    in a JSON format compatible with developer.overheid.nl.
    """

    schema = None  # exclude from schema

    # Restrict available formats to JSON and api
    renderer_classes = [HALJSONRenderer, BrowsableAPIRenderer]

    # For browsable API
    name = "DSO-API"
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
    )

    # Set by as_view
    api_type = "rest_json"

    def get_datasets(self) -> Iterable[Dataset]:
        return get_active_datasets().order_by("name")

    def get_environments(self, ds: Dataset, base: str) -> List[dict]:
        return [
            {
                "name": "production",
                "api_url": base + reverse(f"dynamic_api:openapi-{ds.schema.id}"),
                "specification_url": "",
                "documentation_url": "",
            }
        ]

    def get_related_apis(self, ds: Dataset, base: str) -> List[dict]:
        """ Get list of other APIs exposing the same dataset """
        return []

    def get(self, request, *args, **kwargs):
        # Data not needed for html view
        if getattr(request, "accepted_media_type", None) == "text/html":
            return Response()

        base = request.build_absolute_uri("/").rstrip("/")
        datasets = self.get_datasets()

        result = {"datasets": {}}
        for ds in datasets:
            result["datasets"][ds.schema.id] = {
                "id": ds.schema.id,
                "short_name": ds.name,
                "service_name": ds.schema.title or ds.name,
                "status": ds.schema.get("status", "Beschikbaar"),
                "description": ds.schema.description or "",
                "tags": ds.schema.get("theme", []),
                "terms_of_use": {
                    "government_only": "auth" in ds.schema,
                    "pay_per_use": False,
                    "license": ds.schema.license,
                },
                "environments": self.get_environments(ds, base),
                "related_apis": self.get_related_apis(ds, base),
                "api_authentication": list(ds.schema.auth) or None,
                "api_type": self.api_type,
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            }

        return Response(result)
