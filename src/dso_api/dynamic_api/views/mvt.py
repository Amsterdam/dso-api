"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

from typing import Tuple

from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.http import Http404
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.utils import to_snake_case, toCamelCase
from vectortiles.postgis.views import MVTView

from dso_api.dynamic_api import permissions


class DatasetMVTIndexView(TemplateView):
    """Overview of available MVT endpoints."""

    template_name = "dso_api/dynamic_api/mvt_index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from ..urls import router

        dataset_names = set(router.all_models.keys())
        datasets = (
            (ds.name, list(self._have_geometry_fields(ds.schema)), ds.schema)
            for ds in Dataset.objects.db_enabled().order_by("name")
            if ds.name in dataset_names
        )
        context["datasets"] = [
            (name, fields, schema) for name, fields, schema in datasets if fields
        ]

        return context

    def _have_geometry_fields(self, schema):
        """Yields names of tables that have a geometry field."""
        for table in schema.tables:
            for field in table.fields:
                if field.is_geo:
                    yield to_snake_case(table.name)


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
