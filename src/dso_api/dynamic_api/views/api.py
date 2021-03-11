"""Rest API views, based on Django-Rest-Framework.

These viewsets handle the main API logic of the server.
The views are dynamically generated from Amsterdam Schema files,
just like the rest of the objects (such as serializers, filtersets and models).

To keep the code readable, all logic is placed in a regular DRF-style viewset
(namely :class:`DynamicApiViewSet`). The :func:`viewset_factory` function then
dynamically generates a subclass for the specific model/endpoint. The same
two-step logic can be found in the serializer and model layer of this application.
"""
from __future__ import annotations

from typing import List, Type

from django.db import models
from django.http import Http404, JsonResponse
from django.utils.translation import gettext as _
from rest_framework import viewsets
from schematools.contrib.django.models import DynamicModel

from dso_api.dynamic_api import filterset, locking, permissions, serializers
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


class TemporalRetrieveModelMixin:
    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.versioned and self.model.is_temporal():
            if self.request.dataset_temporal_slice is not None:
                temporal_value = self.request.dataset_temporal_slice["value"]
                start_field, end_field = self.request.dataset_temporal_slice["fields"]
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

        pk = self.kwargs.get("pk")
        pk_field = self.request.dataset.identifier
        if pk_field != "pk":
            queryset = queryset.filter(
                models.Q(**{pk_field: pk}) | models.Q(pk=pk)
            )  # fallback to full id search.
        else:
            queryset = queryset.filter(pk=pk)

        identifier = self.request.dataset.temporal.get("identifier", None)

        # Filter queryset using GET parameters, if any.
        for field in queryset.model._table_schema.fields:
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
    """

    dataset_id = None
    table_id = None

    #: Make sure composed keys like (112740.024|487843.078) are allowed.
    #: The DefaultRouter won't allow '.' in URLs because it's used as format-type.
    lookup_value_regex = r"[^/]+"

    #: Define the model class to use (e.g. in .as_view() call / subclass)
    model: Type[DynamicModel] = None

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    @property
    def paginator(self):
        if (
            self.request.accepted_renderer.unlimited_page_size
            and self.pagination_class.page_size_query_param not in self.request.GET
        ):
            # Avoid expensive COUNT(*) for CSV and GeoJSON formats,
            # return all pages by default, unless an explicit page size is requested.
            return None

        return super().paginator


def _get_viewset_api_docs(
    serializer_class: Type[serializers.DynamicSerializer],
    filterset_class: Type[filterset.DynamicFilterSet],
    ordering_fields: list,
) -> str:
    """Generate the API documentation header for the viewset.
    This documentation is also shown in the Swagger / DRF HTML browser.
    """
    lines = []
    if filterset_class and filterset_class.base_filters:
        lines.append("The following fields can be used as filter with `?FIELDNAME=...`:\n")
        for name, filter_field in filterset_class.base_filters.items():
            description = filter_field.label  # other kwarg appear in .extra[".."]
            lines.append(f"* {name}=*{description}*")

    embedded_fields = getattr(serializer_class.Meta, "embedded_fields", [])
    if embedded_fields:
        if lines:
            lines.append("")
        lines.append("The following fields can be expanded with `?_expandScope=...`:\n")
        lines.extend(f"* {name}" for name in embedded_fields)
        lines.append("\nExpand everything using `_expand=true`.")

    lines.append(
        "\nUse `?_fields=field1,field2` to limit which fields to receive,"
        "\nor `?_fields=-field3,-field4` to exclude specific fields from the response"
    )

    if ordering_fields:
        lines.append("\nUse `?_sort=field,field2,-field3` to sort on fields")

    return "\n".join(lines)


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
    """Generate the viewset for a schema."""
    serializer_class = serializers.serializer_factory(model)
    filterset_class = filterset.filterset_factory(model)
    ordering_fields = _get_ordering_fields(serializer_class)

    attrs = {
        "__doc__": _get_viewset_api_docs(serializer_class, filterset_class, ordering_fields),
        "model": model,
        "queryset": model.objects.all(),  # also for OpenAPI schema parsing.
        "serializer_class": serializer_class,
        "filterset_class": filterset_class,
        "ordering_fields": ordering_fields,
        "dataset_id": model._dataset_schema["id"],
        "table_id": model._table_schema["id"],
    }
    return type(f"{model.__name__}ViewSet", (DynamicApiViewSet,), attrs)
