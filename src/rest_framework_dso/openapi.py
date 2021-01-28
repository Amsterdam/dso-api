"""Improve the OpenAPI schema output """
import logging
from typing import List

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from drf_spectacular import openapi
from drf_spectacular.types import OpenApiTypes, resolve_basic_type
from drf_spectacular.utils import ExtraParameter
from rest_framework import serializers
from rest_framework.fields import ReadOnlyField
from rest_framework.settings import api_settings
from rest_framework_gis.fields import GeometryField

from rest_framework_dso.fields import LinksField

logger = logging.getLogger(__name__)

__all__ = ["DSOSchemaGenerator", "DSOAutoSchema"]

GEOS_TO_GEOJSON = {}
GEOJSON_TYPES = [
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
]
GEOM_TYPES_TO_GEOJSON = {x.upper(): x for x in GEOJSON_TYPES}


class DSOSchemaGenerator(openapi.SchemaGenerator):
    """Extended OpenAPI schema generator, that includes:

    - GeoJSON components
    - Override OpenAPI parts
    """

    #: Allow to override the schema
    schema_overrides = {}

    schema_override_components = {
        "_SelfLink": {
            "type": "object",
            "properties": {
                "self": {
                    "type": "object",
                    "properties": {
                        "href": {
                            "type": "string",
                            "readOnly": True,
                        },
                        "title": {
                            "type": "string",
                            "format": "uri",
                            "readOnly": True,
                        },
                    },
                }
            },
        },
        # Used from https://gist.github.com/codan-telcikt/e1d59ccc9a3af83e083f1a514c84026c
        # Parsed with yaml.load()
        "Geometry": {
            "type": "object",
            "description": "GeoJSON geometry",
            "discriminator": {"propertyName": "type"},
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": GEOJSON_TYPES,
                    "description": "the geometry type",
                }
            },
        },
        "Point3D": {
            "type": "array",
            "description": "Point in 3D space",
            "minItems": 2,
            "maxItems": 3,
            "items": {"type": "number"},
        },
        "Point": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {"properties": {"coordinates": {"$ref": "#/components/schemas/Point3D"}}},
            ],
        },
        "LineString": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Point3D"},
                        }
                    }
                },
            ],
        },
        "Polygon": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Point3D"},
                            },
                        }
                    }
                },
            ],
        },
        "MultiPoint": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Point3D"},
                        }
                    }
                },
            ],
        },
        "MultiLineString": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Point3D"},
                            },
                        }
                    }
                },
            ],
        },
        "MultiPolygon": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Point3D"},
                                },
                            },
                        }
                    }
                },
            ],
        },
        "GeometryCollection": {
            "type": "object",
            "description": "GeoJSON geometry collection",
            "required": ["type", "geometries"],
            "properties": {
                "type": {"type": "string", "enum": ["GeometryCollection"]},
                "geometries": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Geometry"},
                },
            },
        },
    }

    extra_schema = {}

    def get_schema(self, request=None, public=False):
        """Provide the missing data that DRF get_schema_view() doesn't yet offer."""
        schema = super().get_schema(request=request, public=public)
        for key, value in self.schema_overrides.items():
            if isinstance(value, dict):
                try:
                    schema[key].update(value)
                except KeyError:
                    schema[key] = value
            else:
                schema[key] = value

        schema["components"]["schemas"].update(self.schema_override_components)
        return schema


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

    def _map_serializer_field(self, method, field) -> dict:  # noqa: C901
        """Transform the serializer field into a OpenAPI definition.
        This method is overwritten to fix some missing field types.
        """
        if not hasattr(field, "_spectacular_annotation"):
            if isinstance(field, LinksField):
                return {"$ref": "#/components/schemas/_SelfLink"}

            # Fix support for missing field types:
            if isinstance(field, serializers.HyperlinkedRelatedField):
                return resolve_basic_type(OpenApiTypes.URI)

            if isinstance(field, GeometryField):
                # or use $ref when examples are included.
                # model_field.geom_type is uppercase
                if hasattr(field.parent.Meta, "model"):
                    model_field = field.parent.Meta.model._meta.get_field(field.source)
                    geojson_type = GEOM_TYPES_TO_GEOJSON.get(model_field.geom_type, "Geometry")
                else:
                    geojson_type = "Geometry"
                return {"$ref": f"#/components/schemas/{geojson_type}"}

            if isinstance(field, ReadOnlyField):
                try:
                    model_field = field.parent.Meta.model._meta.get_field(field.source)
                except FieldDoesNotExist:
                    pass
                else:
                    return self._map_model_field(model_field)

        return super()._map_serializer_field(method, field)

    def _map_model_field(self, field) -> dict:
        """Transform model fields into an OpenAPI definition.
        This method is overwritten to fix some missing field types.
        """
        if isinstance(field, models.CharField):
            return resolve_basic_type(OpenApiTypes.STR)
        elif isinstance(field, models.ForeignKey):
            return self._map_model_field(field.target_field)

        return super()._map_model_field(field)

    def get_extra_parameters(self, path, method):
        """Expose the DSO-specific HTTP headers in all API methods."""
        extra = [
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
            {
                "in": ExtraParameter.QUERY,
                "name": api_settings.URL_FORMAT_OVERRIDE,
                "schema": {
                    "type": "string",
                    "enum": [
                        renderer.format
                        for renderer in self.view.renderer_classes
                        if renderer.format != "api"  # Exclude browser view
                    ],
                },
                "description": "Select the export format",
                "required": False,
            },
        ]

        return extra

    def _map_field_validators(self, field, schema):
        super()._map_field_validators(field, schema)
        if schema.get("format") == "uri" and "pattern" in schema:
            # In Python, the token \Z does what \z does in other engines.
            # https://stackoverflow.com/questions/53283160
            # Fixed in DRF 3.12.0
            schema["pattern"] = schema["pattern"].replace("\\Z", "\\z")
