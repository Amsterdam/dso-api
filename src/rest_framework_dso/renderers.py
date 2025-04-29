"""The output rendering for the DSO library.

This makes sure the response gets the desired ``application/hal+json``
"""

from datetime import datetime
from io import BytesIO
from types import GeneratorType

import orjson
from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from django.utils.timezone import get_current_timezone
from rest_framework import renderers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.serializers import ListSerializer, Serializer, SerializerMethodField
from rest_framework.utils.breadcrumbs import get_breadcrumbs as drf_get_breadcrumbs
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_csv.renderers import CSVStreamingRenderer
from rest_framework_gis.fields import GeoJsonDict

from rest_framework_dso import pagination
from rest_framework_dso.crs import CRS84, WGS84
from rest_framework_dso.exceptions import HumanReadableException
from rest_framework_dso.fields import GeoJSONIdentifierField
from rest_framework_dso.serializer_helpers import ReturnGenerator

BROWSABLE_MAX_PAGE_SIZE = 1000
DEFAULT_CHUNK_SIZE = 4096


def get_data_serializer(data) -> Serializer | None:
    """Find the serializer associated with the incoming 'data'"""
    if isinstance(data, (ReturnDict, ReturnList, ReturnGenerator)):
        serializer = data.serializer
        if isinstance(serializer, ListSerializer):
            # DSOListSerializer may return a dict, so have a separate check here.
            serializer = serializer.child

        return serializer
    else:
        return None


class RendererMixin:
    """Extra attributes on renderers in this project."""

    unlimited_page_size = False
    supports_list_embeds = True
    supports_detail_embeds = True
    supports_inline_embeds = False
    supports_m2m = True
    compatible_paginator_classes = None
    content_disposition: str | None = None
    default_crs = None
    paginator = None

    chunk_size = DEFAULT_CHUNK_SIZE  # allow to overrule in unit tests

    def setup_pagination(self, paginator: pagination.DelegatedPageNumberPagination):
        """Used by DelegatedPageNumberPagination"""
        self.paginator = paginator

    def tune_serializer(self, serializer: Serializer):
        """Allow to fine-tune the serializer (e.g. remove unused fields).
        This hook is used so the 'fields' are properly set before the peek_iterable()
        is called - as that would return the first item as original.
        """

    def render_exception(self, exception):
        """Inform the client that the stream processing was interrupted with an exception.
        The exception can be rendered in the format fits with the output.

        Purposefully, not much information is given, so avoid informing clients.
        The actual exception is still raised and logged server-side.
        """
        if settings.DEBUG:
            return f"/* Aborted by {exception.__class__.__name__}: {exception} */\n"
        elif isinstance(exception, HumanReadableException):
            # These errors may give a detailed message because it has no sensitive data.
            cause = exception.__cause__ if exception.__cause__ is not None else exception
            return f"/* Aborted by {cause.__class__.__name__}: {exception} */\n"
        else:
            return f"/* Aborted by {exception.__class__.__name__} during rendering! */\n"

    def finalize_response(self, response, renderer_context: dict):
        """Make final adjustments to the response."""
        for name, value in self.get_http_headers(renderer_context).items():
            response[name] = value
        return response

    def get_http_headers(self, renderer_context: dict):
        """Return the http headers for the response."""
        if self.content_disposition:
            now = datetime.now(tz=get_current_timezone()).isoformat()
            dataset_id = renderer_context.get("dataset_id", "dataset")
            table_id = renderer_context.get("table_id", "table")
            return {
                "Content-Disposition": self.content_disposition.format(
                    filename=f"{dataset_id}-{table_id}-{now}"
                )
            }
        return {}


class BrowsableAPIRenderer(RendererMixin, renderers.BrowsableAPIRenderer):
    template = "dso_api/dynamic_api/api.html"

    def get_context(self, data, accepted_media_type, renderer_context):
        context = super().get_context(data, accepted_media_type, renderer_context)

        formats = context["available_formats"]
        if "api" in formats:
            formats.remove("api")

        # Maintain compatibility with other types of ViewSets
        context["authorization_grantor"] = getattr(context["view"], "authorization_grantor", None)
        context["oauth_url"] = settings.OAUTH_URL

        # Insert formatter into context
        if (
            response_formatter := getattr(context["view"], "response_formatter", None)
        ) is not None:
            context["response_formatter"] = "dso_api/dynamic_api/js/" + response_formatter + ".js"

        if dataset_id := getattr(context["view"], "dataset_id", False):
            context["dataset_url"] = reverse(f"dynamic_api:openapi-{dataset_id}-noslash")

        # Fix response content-type when it's filled in by the exception_handler
        response = renderer_context["response"]
        if response.content_type:
            context["response_headers"]["Content-Type"] = response.content_type

        return context

    def get_breadcrumbs(self, request):
        """
        Given a request returns a list of breadcrumbs, which are each a
        tuple of (name, url).

        Extends the buildin function by using instance title from _links
        for the last breadcrumb instead of the generic "Instance".
        """
        
        breadcrumbs = drf_get_breadcrumbs(request.path)
        # Remove duplicates that is generated by the trailing slash
        filtered_breadcrumbs = []
        for i, crumb in enumerate(breadcrumbs):
            if i > 0 and crumb[0] == breadcrumbs[i-1][0] and crumb[1].rstrip('/') == breadcrumbs[i-1][1].rstrip('/'):
                continue
            filtered_breadcrumbs.append(crumb)
        
        filtered_breadcrumbs[-1] = (self.get_name(self.renderer_context["view"]), filtered_breadcrumbs[-1][1])
        return filtered_breadcrumbs

    def render(self, data, accepted_media_type=None, renderer_context=None):
        ret = super().render(
            data,
            accepted_media_type=accepted_media_type,
            renderer_context=renderer_context,
        )

        # Make sure the browsable API always returns text/html
        # by default it falls back to the current media,
        # unless the response (e.g. exception_handler) has overwritten the type.
        response = renderer_context["response"]
        response["content-type"] = "text/html; charset=utf-8"
        return ret


class HALJSONRenderer(RendererMixin, renderers.JSONRenderer):
    media_type = "application/hal+json"

    # Define the paginator per media type.
    compatible_paginator_classes = [pagination.DSOPageNumberPagination]

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Render the data as streaming."""
        if data is None:
            return

        yield from _chunked_output(self._render_json(data), chunk_size=self.chunk_size)

    def _get_footer(self) -> dict:
        """Get the footer"""
        if self.paginator:
            return self.paginator.get_footer()
        return None

    def _render_json(self, data, top=True):  # noqa: C901
        if not data:
            yield orjson.dumps(data)
            return
        elif isinstance(data, dict):
            # Streaming output per key, which can be a whole list in case of embedding
            sep = b"{\n  "
            for key, value in data.items():
                if hasattr(value, "__iter__") and not isinstance(value, str):
                    # Recurse streaming for actual complex values.
                    yield b"%b%b:" % (sep, orjson.dumps(key))
                    yield from self._render_json(value, top=False)
                else:
                    yield sep + orjson.dumps({key: value})[1:-1]
                sep = b",\n  "
            if top and (footer := self._get_footer()) is not None:
                yield sep + orjson.dumps(footer)[1:-1]
            yield b"\n}"
        elif hasattr(data, "__iter__") and not isinstance(data, str):
            # Streaming per item, outputs each record on a new row.
            yield b"["
            sep = b"\n  "
            for item in data:
                yield sep + orjson.dumps(item)
                sep = b",\n  "

            yield b"\n]"
        else:
            yield orjson.dumps(data)

        if top:
            yield b"\n"


class CSVRenderer(RendererMixin, CSVStreamingRenderer):
    """Overwritten CSV renderer to provide proper headers.

    In the view methods (e.g. ``get_renderer_context()``), the serializer
    layout is not accessible. Hence the header is reformatted within a custom
    output renderer.
    """

    unlimited_page_size = True
    supports_list_embeds = False
    supports_detail_embeds = True
    supports_inline_embeds = True
    supports_m2m = False
    compatible_paginator_classes = [pagination.DSOHTTPHeaderPageNumberPagination]
    content_disposition = 'attachment; filename="{filename}.csv"'

    def tune_serializer(self, serializer: Serializer):
        # Serializer type is known, introduce better CSV header column.
        # Avoid M2M content, and skip HAL URL fields as this improves performance.
        csv_fields = {}

        for name, field in serializer.fields.items():
            if name not in ("schema", "_links") and not isinstance(
                field,
                (HyperlinkedRelatedField, SerializerMethodField, ListSerializer),
            ):
                csv_fields[name] = field

                # Make sure sub resources are also trimmed
                if isinstance(field, Serializer):
                    self.tune_serializer(field)

        serializer.fields = csv_fields

    def _get_csv_header(self, serializer: Serializer, request: HttpRequest | None = None):
        """Build the CSV header, including fields from sub-resources.

        If a _fields parameter is present on the request and it doesn't exclude a field,
        we use that as the header, but still loop over the serializer fields to get the
        labels.
        """
        header = []
        labels = {}
        extra_headers = []  # separate list to append at the end.
        extra_labels = {}
        requested_fields = (
            [
                f
                for f in request.GET.get("_fields", "").split(",")
                if not f.startswith("-") and f != ""
            ]
            if request
            else None
        )
        for name, field in serializer.fields.items():
            if isinstance(field, Serializer):
                sub_header, sub_labels = self._get_csv_header(field)
                extra_headers.extend(f"{name}.{sub_name}" for sub_name in sub_header)
                extra_labels.update(
                    {
                        f"{name}.{sub_name}": f"{field.label}.{sub_label}"
                        for sub_name, sub_label in sub_labels.items()
                    }
                )
            else:
                header.append(name)
                labels[name] = field.label
        if requested_fields:
            # Only at the top-level of the recursion, field ordering can be redefined
            return requested_fields, labels | extra_labels
        else:
            return header + extra_headers, labels | extra_labels

    def render(self, data, media_type=None, renderer_context=None):
        if (serializer := get_data_serializer(data)) is not None:
            request = renderer_context.get("request")
            header, labels = self._get_csv_header(serializer, request)

            renderer_context = {**(renderer_context or {}), "header": header, "labels": labels}

        output = super().render(data, media_type=media_type, renderer_context=renderer_context)

        # This method must have a "yield" statement so finalize_response() can
        # recognize this renderer returns a generator/stream, and patch the
        # response.streaming attribute accordingly.
        yield from _chunked_output(output, chunk_size=self.chunk_size)

    def render_exception(self, exception: Exception):
        """Inform clients that the stream was interrupted by an exception.
        The actual exception is still raised and logged.
        Purposefully little information is given to the client.
        """
        if settings.DEBUG:
            return f"\n\nAborted by {exception.__class__.__name__}: {exception}\n"
        elif isinstance(exception, HumanReadableException):
            # These errors may give a detailed message because it has no sensitive data.
            cause = exception.__cause__ if exception.__cause__ is not None else exception
            return f"\n\nAborted by {cause.__class__.__name__}: {exception}\n"
        else:
            return f"\n\nAborted by {exception.__class__.__name__} during rendering!\n"


class GeoJSONRenderer(RendererMixin, renderers.JSONRenderer):
    """Convert the output into GeoJSON notation."""

    unlimited_page_size = True
    supports_detail_embeds = False
    media_type = "application/geo+json"
    format = "geojson"
    charset = "utf-8"

    default_crs = CRS84  # GeoJSON default is urn:ogc:def:crs:OGC::CRS84; axis longitude/latitude
    compatible_paginator_classes = [pagination.DelegatedPageNumberPagination]
    content_disposition = 'attachment; filename="{filename}.json"'

    def tune_serializer(self, serializer: Serializer):
        """Remove unused fields from the serializer:"""
        serializer.fields = {
            name: field for name, field in serializer.fields.items() if name != "_links"
        }

        # Inject an extra field in the serializer to retrieve the object ID.
        if serializer.Meta.model:
            id_field = GeoJSONIdentifierField()
            id_field.bind("__id__", serializer)
            serializer.fields["__id__"] = id_field

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Render `data` into JSON, returning a bytestring.
        """
        if data is None:
            return b""

        request = renderer_context.get("request") if renderer_context else None
        yield from _chunked_output(self._render_geojson(data, request), chunk_size=self.chunk_size)

    def _render_geojson(self, data, request=None):
        # Detect what kind of data is actually provided:
        if isinstance(data, dict):
            if len(data) > 4:
                # Must be a detail page.
                yield self._render_geojson_detail(data, request=request)
                return

            # If it's a listing, remove the _embed wrapper.
            collections = data.get("_embed", data)
        elif isinstance(data, (list, ReturnGenerator, GeneratorType)):
            collections = {"gen": data}
        else:
            raise NotImplementedError(f"Unsupported GeoJSON format: {data.__class__.__name__}")

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
        for _feature_type, features in collections.items():
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
                yield b',\n  "features": [\n    '
            else:
                # Add separator between feature collections.
                yield b",\n"

            # Detect the geometry field from the first feature.
            geometry_field = self._find_geometry_field(first_feature)

            # Output all features, with separator in between.
            yield orjson.dumps(self._item_to_feature(first_feature, geometry_field))
            yield from (
                b",\n    %b" % orjson.dumps(self._item_to_feature(feature, geometry_field))
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
                # The GeoJSON standard mandates coordinates are always in x/y ordering.
                # Thus, it makes sense GEOSGeometry.json always returns coordinates like that.
                # Make sure the crs value reflects that; WGS84 uses (y/x) and CRS84 uses (x/y).
                if content_crs == WGS84:
                    content_crs = CRS84

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
        """Reorganize the dict of a single item."""
        id_value = item.pop("__id__", None)
        feature = {"type": "Feature"}

        if id_value is not None:
            feature["id"] = id_value

        if geometry_field is not None:
            feature["geometry"] = item.pop(geometry_field)

        feature["properties"] = item
        return feature

    def _find_geometry_field(self, properties: dict):
        """Find the first field which contains the geometry of a feature."""
        return next(
            (key for key, value in properties.items() if isinstance(value, GeoJsonDict)),
            None,
        )


def _chunked_output(stream, chunk_size=DEFAULT_CHUNK_SIZE, write_exception=None):
    """Output in larger chunks to avoid many small writes or back-forth calls
    between the WSGI server write code and the original generator function.
    Inspired by django-gisserver logic which applies the same trick.
    """
    buffer = BytesIO()
    try:
        for row in stream:
            buffer.write(row)

            # Calling buffer.tell() is faster than tracking the buffer size in a local integer,
            # because integer addition means allocating a new object.
            if buffer.tell() > chunk_size:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)
        if buffer.tell():
            yield buffer.getvalue()
    except Exception as e:  # noqa: B902
        # Write the last bit that gives some hint on where it stalled:
        if buffer.tell():
            yield buffer.getvalue()

        # Make sure some indication of an exception is also written to the stream.
        # Otherwise, the response is just cut off without any indication what happened.
        if write_exception is not None:
            yield write_exception(e)
        raise
