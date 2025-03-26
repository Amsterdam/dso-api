from collections.abc import Generator
from itertools import chain

from django.contrib.gis.db.models.functions import Transform
from django.db import connections
from django.http import HttpResponse, StreamingHttpResponse
from django.views import View
from vectortiles.backends import BaseVectorLayerMixin
from vectortiles.backends.postgis.functions import AsMVTGeom, MakeEnvelope
from vectortiles.mixins import BaseVectorTileView


class StreamingVectorLayer(BaseVectorLayerMixin):
    """Layer that yields chunked vector tiles.

    Extends the django-vectortiles base mixin. The SQL query differs from
    the VectorLayer class to accommodate a streaming response. That is also
    why we `yield` chunks.
    """

    def __init__(self, id, model, queryset, geom_field, tile_fields):
        self.id = id
        self.model = model
        self.queryset = queryset
        self.geom_field = geom_field
        self.tile_fields = tile_fields

    def get_tile(self, x, y, z) -> Generator[memoryview]:
        if not self.check_in_zoom_levels(z):
            return
        features = self.get_vector_tile_queryset(z, x, y)
        # get tile coordinates from x, y and z
        xmin, ymin, xmax, ymax = self.get_bounds(x, y, z)
        # keep features intersecting tile
        filters = {
            # GeoFuncMixin implicitly transforms to SRID of geom
            f"{self.geom_field}__intersects": MakeEnvelope(xmin, ymin, xmax, ymax, 3857)
        }
        features = features.filter(**filters)
        # annotate prepared geometry for MVT
        features = features.annotate(
            geom_prepared=AsMVTGeom(
                Transform(self.geom_field, 3857),
                MakeEnvelope(xmin, ymin, xmax, ymax, 3857),
                self.tile_extent,
                self.tile_buffer,
                self.clip_geom,
            )
        )
        fields = (
            self.get_tile_fields() + ("geom_prepared",)
            if self.get_tile_fields()
            else ("geom_prepared",)
        )
        # limit feature number if limit provided
        limit = self.get_queryset_limit()
        if limit:
            features = features[:limit]
        # keep values to include in tile (extra included_fields + geometry)
        features = features.values(*fields)
        # generate MVT
        sql, params = features.query.sql_with_params()
        with connections[features.db].cursor() as cursor:
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
                params=[
                    self.get_id(),
                    self.tile_extent,
                    "geom_prepared",
                    *params,
                ],
            )
            for chunk in cursor:
                yield chunk[0]


class StreamingMVTView(BaseVectorTileView, View):
    def get(self, request, z, x, y, *args, **kwargs):
        """
        Handle GET request to serve tile

        :param request:
        :type request: HttpRequest
        :param x: longitude coordinate tile
        :type x: int
        :param y: latitude coordinate tile
        :type y: int
        :param z: zoom level
        :type z: int

        :rtype StreamingHTTPResponse | HTTPResponse
        """
        content, status = self.get_content_status(int(z), int(x), int(y))
        if status == 200:
            return StreamingHttpResponse(
                streaming_content=content, content_type=self.content_type, status=status
            )
        return HttpResponse(content=content, content_type=self.content_type, status=status)

    def get_layer_tiles(self, z, x, y) -> Generator[memoryview]:
        layers: list[StreamingVectorLayer] = self.get_layers()
        if layers:
            for layer in layers:
                yield from layer.get_tile(x, y, z)
        else:
            raise Exception("No layers defined")

    def get_content_status(self, z, x, y):
        streaming_content = self.get_layer_tiles(z, x, y)
        try:
            chunk = next(streaming_content)
        except StopIteration:
            return (b"", 204)
        streaming_content = chain((chunk,), streaming_content)
        return (streaming_content, 200)
