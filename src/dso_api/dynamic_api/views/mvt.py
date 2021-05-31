"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

from typing import Tuple

from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls.base import reverse
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.utils import to_snake_case, toCamelCase
from vectortiles.postgis.views import MVTView

from dso_api.dynamic_api import permissions
from dso_api.dynamic_api.datasets import get_published_datasets
from dso_api.dynamic_api.views import APIIndexView


def get_geo_tables(schema):
    """Yields names of tables that have a geometry field."""
    for table in schema.tables:
        for field in table.fields:
            if field.is_geo:
                yield to_snake_case(table.name)


class DatasetMVTIndexView(APIIndexView):
    """Overview of available MVT endpoints."""

    name = "DSO-API MVT endpoints"  # for browsable API.
    description = "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>.\
        For information on using MVT Tiles see documentation at \
        https://api.data.amsterdam.nl/v1/docs/generic/mvt.html"
    api_type = "MVT"

    def get_datasets(self):
        return [ds for ds in get_published_datasets().order_by("name") if ds.has_geometry_fields]

    def get_environments(self, ds: Dataset, base: str):
        return [
            {
                "name": "production",
                "api_url": base
                + reverse("dynamic_api:mvt-single-dataset", kwargs={"dataset_name": ds.name}),
                "specification_url": base
                + reverse("dynamic_api:mvt-single-dataset", kwargs={"dataset_name": ds.name}),
                "documentation_url": f"{base}/v1/docs/generic/mvt.html",
            }
        ]

    def get_related_apis(self, ds: Dataset, base: str):
        related_apis = [
            {
                "type": "rest_json",
                "url": base + reverse(f"dynamic_api:openapi-{ds.schema.id}"),
            },
            {
                "type": "WFS",
                "url": base + reverse("dynamic_api:wfs", kwargs={"dataset_name": ds.name}),
            },
        ]
        return related_apis


class DatasetMVTSingleView(TemplateView):
    """Shows info about a dataset and its geo-tables."""

    template_name = "dso_api/dynamic_api/mvt_single.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ds = get_object_or_404(Dataset, name=kwargs["dataset_name"])

        geo_tables = sorted(get_geo_tables(ds.schema))

        if len(geo_tables) == 0:
            raise Http404("Dataset does not support MVT") from None

        context["name"] = ds.name
        context["tables"] = geo_tables
        context["schema"] = ds.schema

        return context


class DatasetMVTView(MVTView):
    """An MVT view for a single dataset."""

    permission_classes = [permissions.HasOAuth2Scopes]

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from ..urls import router

        dataset_name = self.kwargs["dataset_name"]
        table_name = self.kwargs["table_name"]

        try:
            model = router.all_models[dataset_name][table_name]
        except KeyError:
            raise Http404("Invalid dataset") from None

        self._unauthorized = permissions.get_unauthorized_fields(request, model)
        self.model = model
        self.check_permissions(request)

    def get(self, request, *args, **kwargs):
        kwargs.pop("dataset_name")
        kwargs.pop("table_name")
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.all()

    @property
    def vector_tile_fields(self) -> Tuple[str]:
        geom_name = self.vector_tile_geom_name
        return tuple(
            f.name
            for f in self.model._meta.get_fields()
            if f.name != geom_name and toCamelCase(f.name) not in self._unauthorized
        )

    @property
    def vector_tile_geom_name(self) -> str:
        for f in self.model._meta.get_fields():
            if isinstance(f, GeometryField):
                return f.name

        raise FieldDoesNotExist()

    def check_permissions(self, request) -> None:
        for permission in self.permission_classes:
            if not permission().has_permission(request, self, [self.model]):
                raise PermissionDenied()
        if self.vector_tile_geom_name in self._unauthorized:
            raise PermissionDenied()
