"""Improvements for the OpenAPI schema output.

While `django-rest-framework <https://www.django-rest-framework.org/>`_ provides OpenAPI support,
it's very limited. That functionality is greatly extended by the use
of `drf-spectacular <https://drf-spectacular.readthedocs.io/>`_ and the classes in this module.
This also inludes exposing geometery type classes in the OpenAPI schema.
"""
import logging

from django.contrib.gis.db import models as gis_models
from drf_spectacular import generators, openapi
from drf_spectacular.contrib.django_filters import DjangoFilterExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter
from rest_framework.settings import api_settings
from rest_framework_gis.fields import GeometryField

from rest_framework_dso import filters
from rest_framework_dso.embedding import get_all_embedded_fields_by_name
from rest_framework_dso.fields import AbstractEmbeddedField
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.serializers import ExpandableSerializer
from rest_framework_dso.views import DSOViewMixin

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


class DSOSchemaGenerator(generators.SchemaGenerator):
    """Extended OpenAPI schema generator, that provides:

    * Override OpenAPI parts (via: :attr:`schema_overrides`)
    * GeoJSON components (added to ``components.schemas``).

    drf_spectacular also provides 'components' which DRF doesn't do.
    """

    #: Allow to override the schema
    schema_overrides = {}

    schema_override_components = {
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
                },
                "coordinates": {
                    "type": "array",
                    "minItems": 2,
                    "description": "Based on the geometry type, a point or collection of points.",
                    "items": {"type": "number"},
                },
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
                {
                    "properties": {
                        "type": {"type": "string", "enum": ["Point"]},
                        "coordinates": {"$ref": "#/components/schemas/Point3D"},
                    }
                },
            ],
        },
        "LineString": {
            "type": "object",
            "description": "GeoJSON geometry",
            "allOf": [
                {"$ref": "#/components/schemas/Geometry"},
                {
                    "properties": {
                        "type": {"type": "string", "enum": ["LineString"]},
                        "coordinates": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Point3D"},
                        },
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
                        "type": {"type": "string", "enum": ["Polygon"]},
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Point3D"},
                            },
                        },
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
                        "type": {"type": "string", "enum": ["MultiPoint"]},
                        "coordinates": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Point3D"},
                        },
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
                    "type": {"type": "string", "enum": ["MultiLineString"]},
                    "properties": {
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Point3D"},
                            },
                        }
                    },
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
                        "type": {"type": "string", "enum": ["MultiPolygon"]},
                        "coordinates": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Point3D"},
                                },
                            },
                        },
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

    def has_view_permissions(self, *args, **kwargs):
        """Schemas are public, so this is always true."""
        return True

    def get_schema(self, request=None, public=False):
        """Improved schema generation, include more OpenAPI fields"""
        schema = super().get_schema(request=request, public=public)

        # Fix missing 'fields' that drf-spectacular doesn't read from self,
        # it only reads the 'SPECTACULAR_SETTINGS' for this.
        if self.version is not None:
            schema["info"]["version"] = self.version
        if self.title is not None:
            schema["info"]["title"] = self.title
        if self.description is not None:
            schema["info"]["description"] = self.description

        # Provide the missing data that DRF get_schema_view() doesn't yet offer.
        self._apply_overrides(schema)
        return schema

    def _apply_overrides(self, schema: dict):
        """Apply any schema overrides defined in the static attributes of this class."""
        for key, value in self.schema_overrides.items():
            if isinstance(value, dict):
                try:
                    schema[key].update(value)
                except KeyError:
                    schema[key] = value
            else:
                schema[key] = value

        # Include geojson field references.
        if components_schemas := schema["components"].get("schemas"):
            components_schemas.update(self.schema_override_components)


class DSOAutoSchema(openapi.AutoSchema):
    """Default schema for API views that don't define a ``schema`` attribute."""

    def get_description(self):
        """Override what _get_viewset_api_docs() does."""
        action = getattr(self.view, "action", self.method.lower())
        if action == "retrieve":
            return ""  # detail view.

        return self.view.table_schema.description or ""

    def get_tags(self) -> 'list[str]':
        """Auto-generate tags based on the path, take last bit of path."""
        tokenized_path = self._tokenize_path()
        return tokenized_path[-1:]

    def _get_paginator(self):
        """Make sure our paginator uses the proper field in the ``_embedded`` schema."""
        paginator = super()._get_paginator()
        if isinstance(paginator, DSOPageNumberPagination):
            paginator.results_field = self.view.serializer_class.Meta.model._meta.model_name

        return paginator

    def _map_model_field(self, model_field, direction):
        schema = super()._map_model_field(model_field, direction=direction)

        if isinstance(model_field, gis_models.GeometryField):
            # In some code paths, drf-spectacular or doesn't even enter _map_serializer_field(),
            # or calls it with a dummy field that doesn't have field.parent. That makes it
            # impossible to resolve the model type. Hence, see if a better type can be resolved
            geojson_type = GEOM_TYPES_TO_GEOJSON.get(model_field.geom_type, "Geometry")
            return {"$ref": f"#/components/schemas/{geojson_type}"}

        return schema

    def _map_serializer_field(self, field, direction, collect_meta=True):
        """Transform the serializer field into a OpenAPI definition.
        This method is overwritten to fix some missing field types.
        """
        if not hasattr(field, "_spectacular_annotation"):
            # Fix support for missing field types:
            if isinstance(field, GeometryField):
                # Not using `rest_framework_gis.schema.GeoFeatureAutoSchema` here,
                # as it duplicates components instead of using $ref.
                if field.parent and hasattr(field.parent.Meta, "model"):
                    # model_field.geom_type is uppercase
                    model_field = field.parent.Meta.model._meta.get_field(field.source)
                    geojson_type = GEOM_TYPES_TO_GEOJSON.get(model_field.geom_type, "Geometry")
                else:
                    geojson_type = "Geometry"
                return {"$ref": f"#/components/schemas/{geojson_type}"}

        return super()._map_serializer_field(field, direction, collect_meta=collect_meta)

    def get_override_parameters(self):
        """Expose the DSO-specific HTTP headers in all API methods."""
        extra = [
            OpenApiParameter(
                name=api_settings.URL_FORMAT_OVERRIDE,
                type={
                    "type": "string",
                    "enum": [
                        renderer.format
                        for renderer in self.view.renderer_classes
                        if renderer.format != "api"  # Exclude browser view
                    ],
                },
                location=OpenApiParameter.QUERY,
                description="Select the export format",
                required=False,
            ),
        ]

        if isinstance(self.view, DSOViewMixin):
            extra += [
                OpenApiParameter(
                    "Accept-Crs",
                    type=OpenApiTypes.STR,
                    location=OpenApiParameter.HEADER,
                    description="Accept-Crs header for Geo queries",
                    required=False,
                ),
                OpenApiParameter(
                    "Content-Crs",
                    type=OpenApiTypes.STR,
                    location=OpenApiParameter.HEADER,
                    description="Content-Crs header for Geo queries",
                    required=False,
                ),
            ]

        # Expose expand parameters too.
        if issubclass(self.view.serializer_class, ExpandableSerializer):
            embeds = get_all_embedded_fields_by_name(self.view.serializer_class)
            examples = []
            if embeds:
                examples = [
                    OpenApiExample(
                        name=dotted_name,
                        value=dotted_name,
                        description=self._get_expand_description(field),
                    )
                    for dotted_name, field in sorted(embeds.items())
                ]
                examples.append(
                    OpenApiExample(
                        name="All Values",
                        value=",".join(sorted(embeds.keys())),
                        description="Expand all fields, identical to only using _expand=true.",
                    )
                )

            extra += [
                OpenApiParameter(
                    "_expand",
                    type=OpenApiTypes.BOOL,
                    location=OpenApiParameter.QUERY,
                    description="Allow to expand relations.",
                    required=False,
                ),
                OpenApiParameter(
                    "_expandScope",
                    type=OpenApiTypes.STR,
                    location=OpenApiParameter.QUERY,
                    description="Comma separated list of named relations to expand.",
                    required=False,
                    examples=examples,
                ),
            ]

        return extra

    def _get_expand_description(self, field: AbstractEmbeddedField):
        """Generate a description for the embed, this uses the help text."""
        if field.is_reverse:
            return field.source_field.target_field.help_text
        else:
            return field.source_field.help_text

    def _map_field_validators(self, field, schema):
        super()._map_field_validators(field, schema)
        if schema.get("format") == "uri" and "pattern" in schema:
            # In Python, the token \Z does what \z does in other engines.
            # https://stackoverflow.com/questions/53283160
            schema["pattern"] = schema["pattern"].replace("\\Z", "\\z")


class DSOFilterExtension(DjangoFilterExtension):
    """A DRF-Spectacular extension that improves the OpenAPI data for django-filter fields.

    This makes sure our extensions to DjangoFilterBackend are still handled by drf-spectacular.
    By default, drf-spectacular only matches filter backends when the class is exactly
    ``django_filters.rest_framework.DjangoFilterBackend``. Subclasses are completely ignored.

    The existence of this class is enough to trigger registration in the extension mechanism.
    Without this class, drf-spectacular calls ``get_schema_operation_parameters()`` directly
    on the filter backend class. Now it's called on this class instead.

    This changes the following OpenAPI data on filter fields from standard django-filter logic:

    * Adds nullable
    * Uses "format: date-time" for datetime filters instead of string.
    * Uses "type: boolean" for isempty/isnull filters instead of string.
    * Uses "type: array", "explode: true" for model-multiple-choice fields (M2M).
    * Removes unneeded "required: false" on filters.
    """

    target_class = filters.DSOFilterBackend
    match_subclasses = True
