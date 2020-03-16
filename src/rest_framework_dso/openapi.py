from typing import List

from drf_spectacular import openapi
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import ExtraParameter


class DSOAutoSchema(openapi.AutoSchema):
    """Default schema for API views that don't define a ``schema`` attribute."""

    def get_tags(self, path, method) -> List[str]:
        """Auto-generate tags based on the path"""
        tokenized_path = self._tokenize_path(path)

        if tokenized_path[0] in {"v1", "1.0"}:
            # Skip a version number in the path
            return tokenized_path[1:2]
        else:
            return tokenized_path[:1]

    def get_extra_parameters(self, path, method):
        """Expose the DSO-specific HTTP headers in all API methods."""
        return [
            ExtraParameter(
                "Accept-Crs",
                type=OpenApiTypes.STR,
                location=ExtraParameter.HEADER,
                description="Accept-Crs header for Geo queries",
                required=False,
            ).to_schema(),
            ExtraParameter(
                "Content-Crs",
                type=OpenApiTypes.STR,
                location=ExtraParameter.HEADER,
                description="Content-Crs header for Geo queries",
                required=False,
            ).to_schema(),
        ]
