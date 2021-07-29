"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

import logging
import time

from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import EmptyResultSet, FieldDoesNotExist, PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls.base import reverse
from django.views.generic import TemplateView
from rest_framework.status import HTTP_204_NO_CONTENT
from schematools.contrib.django.models import Dataset, get_field_schema
from schematools.utils import to_snake_case
from vectortiles.postgis.views import MVTView

from dso_api.dynamic_api.datasets import get_active_datasets
from dso_api.dynamic_api.permissions import CheckPermissionsMixin
from dso_api.dynamic_api.views import APIIndexView

logger = logging.getLogger(__name__)


class DatasetMVTIndexView(APIIndexView):
    """Overview of available MVT endpoints."""

    name = "DSO-API MVT endpoints"  # for browsable API.
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
        "For information on using MVT tiles, see the documentation at "
        "<https://api.data.amsterdam.nl/v1/docs/generic/mvt.html>."
    )
    api_type = "MVT"

    def get_datasets(self):
        return [ds for ds in get_active_datasets().order_by("name") if ds.has_geometry_fields]

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
            raise Http404("Invalid dataset") from None

        self.model = model
        self.check_permissions(request, [self.model])
        self._zoom = int(kwargs["z"])

    def get(self, request, *args, **kwargs):
        kwargs.pop("dataset_name")
        kwargs.pop("table_name")

        t0 = time.perf_counter_ns()
        try:
            result = super().get(request, *args, **kwargs)
            logging.info(
                "retrieved tile for %s (%d bytes) in %.3fs",
                request.path,
                len(result.content),
                (time.perf_counter_ns() - t0) * 1e-9,
            )
            return result
        except EmptyResultSet:  # Raised for self.model.objects.none().query.sql_with_params().
            return HttpResponse(None, content_type=self.content_type, status=HTTP_204_NO_CONTENT)

    def get_queryset(self):
        zoom = self.model.table_schema().zoom
        qs = self.model.objects

        if isinstance(zoom.min, int) and self._zoom < zoom.min:
            return qs.none()
        if isinstance(zoom.max, int) and self._zoom > zoom.max:
            return qs.none()

        if isinstance(zoom.min, str):
            qs = qs.filter(**{zoom.min + "__lte": self._zoom})
        if isinstance(zoom.max, str):
            qs = qs.filter(**{zoom.max + "__gte": self._zoom})

        return qs.all()

    @property
    def vector_tile_fields(self) -> tuple[str]:
        geom_name = self.vector_tile_geom_name
        user_scopes = self.request.user_scopes
        return tuple(
            f.name
            for f in self.model._meta.get_fields()
            if f.name != geom_name and user_scopes.has_field_access(get_field_schema(f))
        )

    @property
    def vector_tile_geom_name(self) -> str:
        for f in self.model._meta.get_fields():
            if isinstance(f, GeometryField):
                return f.name

        raise FieldDoesNotExist()

    def check_permissions(self, request, models) -> None:
        """Override CheckPermissionsMixin to add extra checks"""
        super().check_permissions(request, models)

        # Check whether the geometry field can be accessed, otherwise reading MVT is pointless.
        model_field = self.model._meta.get_field(self.vector_tile_geom_name)
        field_schema = get_field_schema(model_field)
        if not self.request.user_scopes.has_field_access(field_schema):
            raise PermissionDenied()
