"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

import logging
import time

from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls.base import reverse
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.exceptions import SchemaObjectNotFound
from schematools.types import DatasetTableSchema
from schematools.utils import to_snake_case
from vectortiles.postgis.views import MVTView

from dso_api.dynamic_api.datasets import get_active_datasets
from dso_api.dynamic_api.permissions import CheckPermissionsMixin

from .index import APIIndexView

logger = logging.getLogger(__name__)


class DatasetMVTIndexView(APIIndexView):
    """Overview of available MVT endpoints."""

    name = "DSO-API MVT endpoints"  # for browsable API.
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
        "For information on using MVT tiles, see the documentation at "
        "<https://api.data.amsterdam.nl/v1/docs/generic/gis.html>."
    )
    api_type = "MVT"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def get_environments(self, ds: Dataset, base: str):
        api_url = reverse("dynamic_api:mvt-single-dataset", kwargs={"dataset_name": ds.schema.id})
        return [
            {
                "name": "production",
                "api_url": base + api_url,
                "specification_url": base + api_url,
                "documentation_url": f"{base}/v1/docs/generic/gis.html",
            }
        ]

    def get_related_apis(self, ds: Dataset, base: str):
        dataset_id = ds.schema.id
        return [
            {
                "type": "rest_json",
                "url": base + reverse(f"dynamic_api:openapi-{dataset_id}"),
            },
            {
                "type": "WFS",
                "url": base + reverse("dynamic_api:wfs", kwargs={"dataset_name": dataset_id}),
            },
        ]


class DatasetMVTSingleView(TemplateView):
    """Shows info about a dataset and its geo-tables."""

    template_name = "dso_api/dynamic_api/mvt_single.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        ds = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=kwargs["dataset_name"]
        )
        geo_tables = sorted(
            to_snake_case(table.name)
            for table in ds.schema.tables
            if any(field.is_geo for field in table.fields)
        )
        if len(geo_tables) == 0:
            raise Http404("Dataset does not support MVT") from None

        context["name"] = ds.name
        context["tables"] = geo_tables
        context["schema"] = ds.schema

        return context


class DatasetMVTView(CheckPermissionsMixin, MVTView):
    """An MVT view for a single dataset."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from ..urls import router

        dataset_name = self.kwargs["dataset_name"]
        table_name = self.kwargs["table_name"]

        try:
            model = router.all_models[dataset_name][table_name]
        except KeyError:
            raise Http404(f"Invalid table: {dataset_name}.{table_name}") from None

        self.model = model
        self.check_permissions(request, [self.model])

    def get(self, request, *args, **kwargs):
        kwargs.pop("dataset_name")
        kwargs.pop("table_name")

        t0 = time.perf_counter_ns()
        result = super().get(request, *args, **kwargs)
        logging.info(
            "retrieved tile for %s (%d bytes) in %.3fs",
            request.path,
            len(result.content),
            (time.perf_counter_ns() - t0) * 1e-9,
        )
        return result

    def get_queryset(self):
        return self.model.objects.all()

    @property
    def vector_tile_fields(self) -> tuple[str]:
        geom_name = self.vector_tile_geom_name
        user_scopes = self.request.user_scopes
        return tuple(
            f.name
            for f in self.model._meta.get_fields()
            if f.name != geom_name and user_scopes.has_field_access(self.model.get_field_schema(f))
        )

    @property
    def vector_tile_geom_name(self) -> str:
        schema: DatasetTableSchema = self.model.table_schema()
        field = schema.main_geometry
        try:
            return to_snake_case(schema.get_field_by_id(field).name)
        except SchemaObjectNotFound as e:
            raise FieldDoesNotExist(f"no field named {field!r}") from e

    def check_permissions(self, request, models) -> None:
        """Override CheckPermissionsMixin to add extra checks"""
        super().check_permissions(request, models)

        # Check whether the geometry field can be accessed, otherwise reading MVT is pointless.
        model_field = self.model._meta.get_field(self.vector_tile_geom_name)
        field_schema = self.model.get_field_schema(model_field)
        if not self.request.user_scopes.has_field_access(field_schema):
            raise PermissionDenied()
