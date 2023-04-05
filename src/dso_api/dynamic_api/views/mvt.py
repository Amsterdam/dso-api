"""Mapbox Vector Tiles (MVT) views of geographic datasets."""

import itertools
import logging
import time
from urllib.parse import unquote

import mercantile
from django.contrib.gis.db.models import functions
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db import connection
from django.db.models import F, Model
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.urls.base import reverse
from django.views import View
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.exceptions import SchemaObjectNotFound
from schematools.naming import toCamelCase
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema
from vectortiles import VectorLayer
from vectortiles.backends import BaseVectorLayerMixin
from vectortiles.backends.postgis.functions import AsMVTGeom, MakeEnvelope
from vectortiles.views import TileJSONView

from dso_api.dynamic_api.datasets import get_active_datasets
from dso_api.dynamic_api.filters.values import AMSTERDAM_BOUNDS, DAM_SQUARE
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
    """Shows an HTML page about a dataset and its geo-tables."""

    template_name = "dso_api/dynamic_api/mvt_single.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            from dso_api.dynamic_api.urls import router

            dataset_name = kwargs["dataset_name"]
            models = router.all_models[dataset_name]
        except KeyError:
            raise Http404(f"Unknown dataset: {dataset_name!r}") from None

        geo_tables = sorted(
            table_name
            for table_name, model in models.items()
            if any(field.is_geo for field in model.table_schema().fields)
        )
        if len(geo_tables) == 0:
            raise Http404("Dataset does not support MVT") from None

        context["name"] = dataset_name
        context["tables"] = geo_tables
        context["schema"] = models[geo_tables[0]].table_schema().dataset
        return context


class DatasetMVTView(CheckPermissionsMixin, View):
    """An MVT view for a single table.
    This view generates the Mapbox Vector Tile format as output.
    """

    _CONTENT_TYPE = "application/vnd.mapbox-vector-tile"
    _EXTENT = 4096  # Default extent for MVT.
    # Name of temporary MVT row that we add to our queryset.
    # No field name starting with an underscore ever occurs in our datasets.
    _MVT_ROW = "_geom_prepared_for_mvt"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from dso_api.dynamic_api.urls import router

        dataset_name = self.kwargs["dataset_name"]
        table_name = self.kwargs["table_name"]

        try:
            model = router.all_models[dataset_name][table_name]
        except KeyError:
            raise Http404(f"Invalid table: {dataset_name}.{table_name}") from None

        schema: DatasetTableSchema = model.table_schema()
        try:
            self._main_geo = schema.main_geometry_field.python_name
        except SchemaObjectNotFound as e:
            raise FieldDoesNotExist(f"No field named '{schema.main_geometry}'") from e

        self.model = model
        self.check_permissions(request, [self.model])

    def get_layers(self) -> list[BaseVectorLayerMixin]:
        """Provide all layer definitions for this rendering."""
        layer: BaseVectorLayerMixin = VectorLayer()
        layer.id = "default"
        layer.model = self.model
        self._schemafy_layer(layer)
        return [layer]

    def get(self, request, *args, **kwargs):
        x, y, z = kwargs["x"], kwargs["y"], kwargs["z"]

        tile = self._stream_tile(x, y, z)
        try:
            chunk = next(tile)
        except StopIteration:
            return HttpResponse(content=b"", content_type=self._CONTENT_TYPE, status=204)
        tile = itertools.chain((chunk,), tile)

        return StreamingHttpResponse(
            streaming_content=tile, content_type=self._CONTENT_TYPE, status=200
        )

    def _schemafy_layer(self, layer: BaseVectorLayerMixin) -> None:
        schema: DatasetTableSchema = self.model.table_schema()
        user_scopes: UserScopes = self.request.user_scopes

        layer.geom_field = schema.main_geometry_field.python_name

        queryset = self.model.objects.all()

        # We always include the identifier fields
        identifiers = schema.identifier_fields
        tile_fields = tuple(id.name for id in identifiers)

        for field in schema.fields:
            field_name = field.name
            if not user_scopes.has_field_access(field):
                # 403
                continue
            if field.is_relation:
                # Here we have to use the db_name, because that usually has a suffix not
                # available on field.name.
                field_name = toCamelCase(field.db_name)
            if (
                self.z >= 15
                and field.db_name != layer.geom_field
                and field.name != "schema"
                and field_name not in tile_fields
            ):
                # If we are zoomed far out (low z), only fetch the geometry field for a
                # smaller payload. The cutoff is arbitrary. Play around with
                # https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/
                # to get a feel for the MVT zoom levels and how much detail a single tile
                # should contain. We exclude the main geometry and `schema` fields.
                tile_fields += (field_name,)

                if field_name != field.db_name and field_name.lower() != field_name:
                    # Annotate camelCased field names so they can be found.
                    queryset = queryset.annotate(**{field_name: F(field.db_name)})
        layer.queryset = queryset
        layer.tile_fields = tile_fields

    def _stream_tile(self, x: int, y: int, z: int):
        qs = self.model.objects.all()
        bbox = MakeEnvelope(*mercantile.xy_bounds(x, y, z), 3857)
        qs = qs.filter(
            **{
                f"{self._main_geo}__intersects": bbox,
            }
        )
        # Add MVT row and restrict to the fields we want in the response.
        qs = qs.annotate(
            **{self._MVT_ROW: AsMVTGeom(functions.Transform(self._main_geo, 3857), bbox)}
        )
        qs = qs.values(self._MVT_ROW, *self._property_fields(z))

        sql, params = qs.query.sql_with_params()
        with connection.cursor() as cursor:
            # This hairy query generates the MVT tile using ST_AsMVT, then breaks it up into rows
            # that we can stream to the client. We do this because the tile is a potentially very
            # large bytea in PostgreSQL, which psycopg would otherwise consume in its entirety
            # before passing it on to us. Since psycopg also needs to keep the hex-encoded
            # PostgreSQL wire format representation of the tile in memory while decoding it, it
            # needs 3*n memory to decode an n-byte tile, and tiles can be up to hundreds of
            # megabytes.
            #
            # To make matters worse, what psycopg returns is a memoryview, and Django accepts
            # memoryviews just fine but casts them to bytes objects, meaning the entire tile gets
            # copied again. That happens after the hex version has been decoded, but it still
            # means a slow client can keep our memory use at 2*n for the duration of the request.
            CHUNK_SIZE = 8192
            cursor.execute(
                f"""
                WITH mvt AS (
                    SELECT ST_AsMVT(_sub.*, %s, %s, %s) FROM ({sql}) as _sub
                )
                SELECT * FROM (
                    /* This is SQL for range(1, len(x), CHUNK_SIZE), sort of. */
                    WITH RECURSIVE chunk(i) AS (
                            VALUES (1)
                        UNION ALL
                            SELECT chunk.i+{CHUNK_SIZE} FROM chunk, mvt
                            WHERE i < octet_length(mvt.ST_AsMVT)
                    ),
                    sorted AS (SELECT * FROM chunk ORDER BY i)
                    SELECT substring(mvt.ST_AsMVT FROM sorted.i FOR {CHUNK_SIZE}) FROM mvt, sorted
                ) AS chunked_mvt WHERE octet_length(substring) > 0
                """,  # noqa: S608
                params=["default", self._EXTENT, self._MVT_ROW, *params],
            )
            for chunk in cursor:
                yield chunk[0]

    def _property_fields(self, z) -> tuple:
        """Returns fields to include in the tile as MVT properties alongside the geometry."""
        # If we are zoomed far out (low z), only fetch the geometry field for a smaller payload.
        # The cutoff is arbitrary. Play around with
        # https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/#14/4.92/52.37
        # to get a feel for the MVT zoom levels and how much detail a single tile should contain.
        if z < 15:
            return ()

        user_scopes = self.request.user_scopes
        return tuple(
            f.name
            for f in self.model._meta.get_fields()
            if f.name != self._main_geo
            and user_scopes.has_field_access(self.model.get_field_schema(f))
        )

    def check_permissions(self, request, models) -> None:
        """Override CheckPermissionsMixin to add extra checks"""
        super().check_permissions(request, models)

        # Check whether the geometry field can be accessed, otherwise reading MVT is pointless.
        if not self.request.user_scopes.has_field_access(
            self.model.table_schema().main_geometry_field
        ):
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
        self.name = dataset_name

        try:
            models = router.all_models[dataset_name]
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
            if field.is_relation:
                # Here we have to use the db_name, because that usually has a suffix not
                # available on field.name.
                field_name = toCamelCase(field.db_name)
            if field_name != "schema":
                # We exclude the main geometry and `schema` fields.
                layer_fields[field_name] = field.type
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
