"""Mapbox Vector Tiles (MVT) views of geographic datasets."""
import itertools
import logging

import mercantile
from django.contrib.gis.db.models import functions
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.db import connection
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.urls.base import reverse
from django.views import View
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.exceptions import SchemaObjectNotFound
from schematools.types import DatasetTableSchema
from vectortiles.postgis.functions import AsMVTGeom, MakeEnvelope

from ..datasets import get_active_datasets
from ..permissions import CheckPermissionsMixin
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
    """An MVT view for a single dataset."""

    _CONTENT_TYPE = "application/vnd.mapbox-vector-tile"
    _EXTENT = 4096  # Default extent for MVT.
    # Name of temporary MVT row that we add to our queryset.
    # No field name starting with an underscore ever occurs in our datasets.
    _MVT_ROW = "_geom_prepared_for_mvt"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        from ..urls import router

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
            cursor.execute(  # nosec
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
                """,
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
        model_field = self.model._meta.get_field(self._main_geo)
        field_schema = self.model.get_field_schema(model_field)
        if not self.request.user_scopes.has_field_access(field_schema):
            raise PermissionDenied()
