"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

import logging
import time
from urllib.parse import unquote

from django.core.exceptions import PermissionDenied
from django.db.models import F, Model
from django.http import Http404
from django.urls.base import reverse
from django.views.generic import TemplateView
from schematools.naming import toCamelCase
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema
from vectortiles import VectorLayer
from vectortiles.backends import BaseVectorLayerMixin
from vectortiles.views import TileJSONView

from dso_api.dynamic_api.constants import DEFAULT
from dso_api.dynamic_api.datasets import get_active_datasets
from dso_api.dynamic_api.filters.values import AMSTERDAM_BOUNDS, DAM_SQUARE
from dso_api.dynamic_api.permissions import CheckModelPermissionsMixin
from dso_api.dynamic_api.views.mvt_base import StreamingMVTView, StreamingVectorLayer

from .index import APIIndexView

logger = logging.getLogger(__name__)


class DatasetMVTIndexView(APIIndexView):
    """Overview of available MVT endpoints."""

    name = "MVT endpoints"  # for browsable API.
    description = (
        "Alle WFS endpoints voor de gegevens in de DSO-API.\n\n"
        "Voor het gebruik van MVT endpoints, zie: "
        "[Datasets laden in GIS-pakketten](/v1/docs/generic/gis.html),"
        " en de algemene [documentatie van de DSO-API](/v1/docs/)."
    )
    api_type = "MVT"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def _build_version_endpoints(
        self, base: str, dataset_id: str, version: str, header: str | None = None, suffix: str = ""
    ):
        kwargs = {"dataset_name": dataset_id, "dataset_version": version}
        mvt_url = reverse(f"dynamic_api:mvt{suffix}", kwargs=kwargs)
        wfs_url = reverse(f"dynamic_api:wfs{suffix}", kwargs=kwargs)
        api_url = reverse(f"dynamic_api:openapi{suffix}", kwargs=kwargs)
        return {
            "header": header or f"Versie {version}",
            "mvt_url": base + mvt_url,
            "doc_url": f"{base}/v1/docs/generic/gis.html",
            "documentation_url": f"{base}/v1/docs/generic/gis.html",  # For catalog
            "api_url": base + api_url,
            "wfs_url": base + wfs_url,
            "specification_url": base + mvt_url,  # For catalog
        }


class DatasetMVTSingleView(TemplateView):
    """Shows an HTML page about a dataset and its geo-tables."""

    template_name = "dso_api/dynamic_api/mvt_dataset.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dataset_version = kwargs["dataset_version"]
        try:
            from dso_api.dynamic_api.urls import router

            dataset_name = kwargs["dataset_name"]
            models = router.all_models[dataset_name][dataset_version]
        except KeyError:
            raise Http404(f"Unknown dataset: {dataset_name!r}") from None

        geo_tables = sorted(
            table_name
            for table_name, model in models.items()
            if any(field.is_geo for field in model.table_schema().fields)
        )
        if len(geo_tables) == 0:
            raise Http404("Dataset does not support MVT") from None

        schema = models[geo_tables[0]].table_schema().dataset
        suffix = "" if dataset_version == DEFAULT else "-version"
        path = self.request.path
        if not path.endswith("/"):
            path += "/"

        context.update(
            {
                "mvt_title": schema.title or dataset_name.title(),
                "schema": schema,
                "tables": geo_tables,
                "version": dataset_version,
                "base_url": self.request.build_absolute_uri("/").rstrip("/"),
                "tilejson_url": reverse(f"dynamic_api:mvt-tilejson{suffix}", kwargs=kwargs),
                "path": path,
                "doc_url": reverse(f"dynamic_api:docs-dataset{suffix}", kwargs=kwargs),
                "wfs_url": reverse(f"dynamic_api:wfs{suffix}", kwargs=kwargs),
            }
        )

        return context


class DatasetMVTView(CheckModelPermissionsMixin, StreamingMVTView):
    """An MVT view for a single table.
    This view streams the Mapbox Vector Tile format as output.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from dso_api.dynamic_api.urls import router

        dataset_name = self.kwargs["dataset_name"]
        dataset_version = self.kwargs["dataset_version"]
        table_name = self.kwargs["table_name"]

        try:
            model = router.all_models[dataset_name][dataset_version][table_name]
        except KeyError:
            raise Http404(f"Invalid table: {dataset_name}.{table_name}") from None

        self._main_geo = model.table_schema().main_geometry_field
        self.model = model
        self.check_model_permissions([self.model])

    def get(self, request, *args, **kwargs):
        self.zoom = kwargs["z"]
        return super().get(request, *args, **kwargs)

    def get_layers(self) -> list[StreamingVectorLayer]:
        """Provide all layer definitions for this rendering."""
        layer = self._create_layer()
        return [layer]

    def _create_layer(self) -> StreamingVectorLayer:
        """Creates the layer used for getting the tiles.

        Adds queryset and tile_fields to the layer.
        Annotates the queryset with some camelCased aliases.
        Determines the fields to include based on zoom.
        """

        schema: DatasetTableSchema = self.model.table_schema()
        user_scopes: UserScopes = self.request.user_scopes
        queryset = self.model.objects.all()

        # We always include the identifier fields
        identifiers = schema.identifier_fields
        tile_fields = tuple(id.name for id in identifiers)

        for field in schema.fields:
            if (
                not user_scopes.has_field_access(field)
                or self.zoom < schema.min_zoom
                or self.zoom > schema.max_zoom
            ):
                # 403 or not within zoom range to include the field.
                continue

            # We may have to use the db_name, because that usually has a suffix not
            # available on field.name.
            field_name = toCamelCase(field.db_name) if field.is_relation else field.name

            # We exclude the main geometry and `schema` fields.
            if (
                field_name not in tile_fields
                and field_name != "schema"
                and field != self._main_geo
            ):
                tile_fields += (field_name,)

                if field_name != field.db_name and field_name.lower() != field_name:
                    # Annotate camelCased field names so they can be found.
                    queryset = queryset.annotate(**{field_name: F(field.db_name)})

        return StreamingVectorLayer(
            id="default",
            model=self.model,
            geom_field=self._main_geo.python_name,
            queryset=queryset,
            tile_fields=tile_fields,
        )

    def check_model_permissions(self, models) -> None:
        """Override CheckPermissionsMixin to add extra checks"""
        super().check_model_permissions(models)

        # Check whether the geometry field can be accessed, otherwise reading MVT is pointless.
        if not self.request.user_scopes.has_field_access(self._main_geo):
            raise PermissionDenied()


class DatasetTileJSONView(TileJSONView):
    """View to serve a tilejson.json file.

    Some values are hardcoded for our usecase.
    """

    attribution = '(c) Gemeente <a href="https://amsterdam.nl">Amsterdam</a>'
    tile_url = "{z}/{x}/{y}.pbf"
    bounds = AMSTERDAM_BOUNDS
    center = DAM_SQUARE
    min_zoom = 7
    max_zoom = 15

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from dso_api.dynamic_api.urls import router

        dataset_name = self.kwargs["dataset_name"]
        dataset_version = self.kwargs["dataset_version"]
        self.name = dataset_name

        try:
            models = router.all_models[dataset_name][dataset_version]
        except KeyError:
            raise Http404(f"Invalid dataset: {dataset_name}") from None

        # Filter models to the ones that have a geo field.
        self.models = list(
            filter(
                lambda model: any(field.is_geo for field in model.table_schema().fields),
                models.values(),
            )
        )
        if len(self.models) == 0:
            raise Http404(f"Dataset {dataset_name} does not have tables with geometry")

        schema = self.models[0].table_schema().schema
        self.description = schema.description
        self.name = schema.title

    def get_layers(self) -> list[BaseVectorLayerMixin]:
        "Override to get all the layer metadata out of the models."
        layers = []
        # models are present after setup(), but BaseTileJSONView accesses get_layers() on init
        if hasattr(self, "models"):
            for model in self.models:
                layer = self._create_layer(model)
                layers.append(layer)

        return sorted(layers, key=lambda layer: layer.id)

    def _create_layer(self, model: Model) -> BaseVectorLayerMixin:
        "Create a layer with all necessary metadata."
        layer: BaseVectorLayerMixin = VectorLayer()
        schema: DatasetTableSchema = model.table_schema()
        layer.id = model.__name__
        layer.min_zoom = self.min_zoom
        layer.max_zoom = self.max_zoom
        layer.description = schema.description

        layer_fields = {}
        for field in schema.fields:
            field_name = field.name
            if field_name == "schema":
                continue

            if field.is_relation:
                # Here we have to use the db_name, because that usually has a suffix not
                # available on field.name.
                field_name = toCamelCase(field.db_name)

            layer_fields[field_name] = field.description or field.type
        layer.layer_fields = layer_fields
        return layer

    def get_tile_urls(self, tile_url):
        "Override to compose tile urls for each model in the dataset."
        urls = []
        for model in self.models:
            url = unquote(self.request.build_absolute_uri(model.__name__ + "/" + self.tile_url))
            urls.append(url)
        return sorted(urls)

    def get(self, request, *args, **kwargs):
        kwargs.pop("dataset_name")

        t0 = time.perf_counter_ns()
        result = super().get(request, *args, **kwargs)
        logging.info(
            "retrieved tileJSON for %s (%d bytes) in %.3fs",
            request.path,
            len(result.content),
            (time.perf_counter_ns() - t0) * 1e-9,
        )
        return result
