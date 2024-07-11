"""Improved input parsing.

This supports the DSO ``Content-Crs`` HTTP header, so HTTP POST requests
can be parsed with the desired coordinate projection.
"""

from rest_framework.exceptions import NotAcceptable
from rest_framework.parsers import JSONParser

from .crs import CRS
from .exceptions import PreconditionFailed
from .renderers import HALJSONRenderer


class GeoDict(dict):
    """A wrapper to provide the CRS data to the ``request.data``."""

    def __init__(self, data: dict, crs: CRS):
        super().__init__(data)
        self.crs = crs


class GeoList(list):
    """A wrapper to provide the CRS data to the ``request.data``."""

    def __init__(self, data: list, crs: CRS):
        super().__init__(data)
        self.crs = crs


class DSOJsonParser(JSONParser):
    """Parse incoming JSON requests.

    This adds an ``request.data.crs`` attribute
    """

    renderer_class = HALJSONRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        # Need to tell which CRS our data stream uses:
        request = parser_context["view"].request
        content_crs = self._get_content_crs(request)

        json_data = super().parse(stream, media_type=media_type, parser_context=parser_context)

        # Store this value for usage by the serializer classes.
        if isinstance(json_data, dict):
            return GeoDict(json_data, crs=content_crs)
        elif isinstance(json_data, list):
            return GeoList(json_data, crs=content_crs)
        else:
            return json_data

    def _get_content_crs(self, request):
        """Fetch the Content-Crs header."""
        http_value = request.headers.get("Content-Crs")
        if not http_value:
            raise PreconditionFailed("The HTTP Content-Crs header is required")

        try:
            return CRS.from_string(http_value)
        except ValueError as e:
            raise NotAcceptable(f"Chosen CRS is invalid: {e}") from e
