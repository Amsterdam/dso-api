from io import BytesIO

import orjson
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.renderers import JSONRenderer
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_csv.renderers import CSVStreamingRenderer
from rest_framework_gis.fields import GeoJsonDict
from rest_framework.serializers import SerializerMethodField

from rest_framework_dso.serializer_helpers import ReturnGenerator
from rest_framework_dso import pagination


class RendererMixin:
    """Extra attributes on renderers in this project."""

    compatible_paginator_classes = None
    default_crs = None
    paginator = None

    def setup_pagination(self, paginator: pagination.DelegatedPageNumberPagination):
        """Used by DelegatedPageNumberPagination"""
        self.paginator = paginator


class HALJSONRenderer(RendererMixin, JSONRenderer):
    media_type = "application/hal+json"

    # Define the paginator per media type.
    compatible_paginator_classes = [pagination.DSOPageNumberPagination]


class CSVRenderer(RendererMixin, CSVStreamingRenderer):
    """Overwritten CSV renderer to provide proper headers.

    In the view methods (e.g. ``get_renderer_context()``), the serializer
    layout is not accessible. Hence the header is reformatted within a custom
    output renderer.
    """

    compatible_paginator_classes = [pagination.DSOHTTPHeaderPageNumberPagination]

    def render(self, data, media_type=None, renderer_context=None):
        if isinstance(data, ReturnDict):
            serializer = data.serializer
        elif isinstance(data, (ReturnList, ReturnGenerator)):
            serializer = data.serializer.child
        else:
            serializer = None

        if serializer is not None:
            # Serializer type is known, introduce better CSV header column.
            renderer_context = {
                **(renderer_context or {}),
                "header": [
                    name
                    for name, field in serializer.fields.items()
                    if name != "schema"
                    and not isinstance(
                        field, (HyperlinkedRelatedField, SerializerMethodField)
                    )
                ],
                "labels": {
                    name: field.label for name, field in serializer.fields.items()
                },
            }

        output = super().render(
            data, media_type=media_type, renderer_context=renderer_context
        )

        # This method must have a "yield" statement so finalize_response() can
        # recognize this renderer returns a generator/stream, and patch the
        # response.streaming attribute accordingly.
        yield from _chunked_output(output)


class GeoJSONRenderer(RendererMixin, JSONRenderer):
    """Convert the output into GeoJSON notation."""

    media_type = "application/geo+json"
    format = "geojson"

    default_crs = "EPSG:4326"  # GeoJSON always defaults to WGS84.
    compatible_paginator_classes = [pagination.DelegatedPageNumberPagination]

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Render `data` into JSON, returning a bytestring.
        """
        if data is None:
            return b""

        request = renderer_context.get("request") if renderer_context else None
        yield from _chunked_output(self._render_geojson(data, request))

    def _render_geojson(self, data, request=None):
        # Detect what kind of data is actually provided:
        if isinstance(data, dict):
            if len(data) > 4:
                # Must be a detail page
                yield self._render_geojson_detail(data, request=request)
                return

            if "_embed" in data:
                # Must be a listing, not a detail view which may also have _embed.
                collections = data["_embed"]
            else:
                collections = {"list": data}
        elif isinstance(data, (list, ReturnGenerator)):
            collections = {"gen": data}
        else:
            raise NotImplementedError(
                f"Unsupported GeoJSON format: {data.__class__.__name__}"
            )

        yield from self._render_geojson_list(collections, request=request)

    def _render_geojson_detail(self, data, request=None):
        # Not a list view. (_embed may also occur in detail views).
        geometry_field = self._find_geometry_field(data)
        return orjson.dumps(
            {
                **self._item_to_feature(data, geometry_field),
                **self._get_crs(request),
            }
        )

    def _render_geojson_list(self, collections, request=None):
        # Learned a trick from django-gisserver: write GeoJSON in bits.
        # Instead of serializing a large dict, each individual item is serialized.
        first_generator = None
        for feature_type, features in collections.items():
            # First a feature needs to be read. This also performs
            # the CRS detection (request.response_content_crs) inside the serializer.
            features_iter = iter(features)
            first_feature = next(features_iter, None)
            if first_feature is None:
                continue  # empty generator

            # When the first feature is found, write the header
            if first_generator is None:
                first_generator = features

                # Now that the CRS can be detected, write out the header.
                yield orjson.dumps(self._get_header(request))[:-1]
                yield b',\n  "features": [\n'
            else:
                # Add separator between feature collections.
                yield b",\n"

            # Detect the geometry field from the first feature.
            geometry_field = self._find_geometry_field(first_feature)

            # Output all features, with separator in between.
            yield orjson.dumps(self._item_to_feature(first_feature, geometry_field))
            yield from (
                b",\n%b" % orjson.dumps(self._item_to_feature(feature, geometry_field))
                for feature in features_iter
            )

        if first_generator is None:
            # No feature detected, nothing is yet written. Output empty response
            yield b"%b\n" % orjson.dumps(
                {
                    **self._get_header(request),
                    "features": [],
                    **self._get_footer(),
                }
            )
        else:
            # Write footer
            footer = self._get_footer()
            yield b"\n  ],\n%b\n" % orjson.dumps(footer)[1:]

    def _get_header(self, request):
        return {
            "type": "FeatureCollection",
            **self._get_crs(request),
            # "_links": is written at the end for better query performance.
        }

    def _get_crs(self, request) -> dict:
        """Generate the CRS section.
        Only old 2008 GeoJSON used this, but using it since the DSO API allows
        to negotiate the CRS it's included.
        """
        if request is not None:
            # Detect which Coordinate Reference System the response is written in.
            accept_crs = getattr(request, "accept_crs", None)
            content_crs = getattr(request, "response_content_crs", None) or accept_crs

            if content_crs is not None:
                return {
                    "crs": {
                        "type": "name",
                        "properties": {"name": str(content_crs)},
                    }
                }

        return {}

    def _get_footer(self):
        """Generate the last fields of the response."""
        return {"_links": self._get_links()}

    def _get_links(self) -> list:
        """Generate the pagination links"""
        links = []

        # The view may choose not to provide pagination at all.
        # Otherwise, use it's knowledge to generate links in the right format here.
        if self.paginator is not None:
            if next_link := self.paginator.get_next_link():
                links.append(
                    {
                        "href": next_link,
                        "rel": "next",
                        "type": "application/geo+json",
                        "title": "next page",
                    }
                )
            if previous_link := self.paginator.get_previous_link():
                links.append(
                    {
                        "href": previous_link,
                        "rel": "previous",
                        "type": "application/geo+json",
                        "title": "previous page",
                    }
                )

        return links

    def _item_to_feature(self, item: dict, geometry_field):
        """Reorganize the dict of a single item"""

        #  get the foreign key relations from the _links field and unpack from its HAL envelope.
        link_properties = {
            key: value["href"]
            for key, value in item["_links"].items()
            if key not in ("self", "schema") and "href" in value
        }
        return {
            "type": "Feature",
            # "id": item
            "geometry": item.pop(geometry_field),
            "properties": {
                **link_properties,
                **{
                    key: value
                    for key, value in item.items()
                    if key not in ("schema", "_links")
                },
            },
        }

    def _find_geometry_field(self, properties: dict):
        """Find the first field which contains the geometry of a feature."""
        return next(
            (
                key
                for key, value in properties.items()
                if isinstance(value, GeoJsonDict)
            ),
            None,
        )


def _chunked_output(stream, chunk_size=4096):
    """Output in larger chunks to avoid many small writes or back-forth calls
    between the WSGI server write code and the original generator function.
    Inspired by django-gisserver logic which applies the same trick.
    """
    buffer = BytesIO()
    buffer_size = 0
    for row in stream:
        buffer.write(row)
        buffer_size += len(row)

        if buffer_size > chunk_size:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            buffer_size = 0

    if buffer_size:
        yield buffer.getvalue()
