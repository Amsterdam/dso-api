"""OpenAPI logic for dynamic filters.

This generates the most common parameters that are allowed for the filters.
More fields as possible, since relations can be followed.
Those fields are not included here.
"""
from __future__ import annotations

import re

from schematools.types import DatasetFieldSchema, DatasetTableSchema

from dso_api.dynamic_api.filters import parser
from dso_api.dynamic_api.filters.parser import QueryFilterEngine

RE_GEOJSON_TYPE = re.compile(r"^https://geojson\.org/schema/(?P<geotype>[a-zA-Z]+)\.json$")

OPENAPI_LOOKUP_TYPES = {
    "isempty": "boolean",
    "isnull": "boolean",
    "like": "string",
}

OPENAPI_COMMA_LOOKUPS = {"in"}

OPENAPI_SCALAR_EXAMPLES = {
    "boolean": "use true or false",
    "string": "text",
    "integer": "number",
    "number": "number",
    "array": "id",
    "object": {},
    # Format variants for type string:
    "date": "use yyyy-mm-dd",
    "time": "use hh:mm[:ss[.ms]]",
    "date-time": "use yyyy-mm-dd or yyyy-mm-ddThh:mm[:ss[.ms]]",
    "uri": "URL",
}

OPENAPI_LOOKUP_PREFIX = {
    "lt": "Less than; ",
    "lte": "Less than or equal to; ",
    "gt": "Greater than; ",
    "gte": "Greater than or equal to; ",
    "not": "Exclude matches; ",
}

OPENAPI_LOOKUP_EXAMPLES = {
    "isempty": "Whether the field is empty or not.",
    "isnull": "Whether the field has a NULL value or not.",
    "like": "Matches text using wildcards (? and *).",
    "in": "Matches any value from a comma-separated list: val1,val2,valN.",
}

OPENAPI_TYPE_LOOKUP_EXAMPLES = {
    "https://geojson.org/schema/Point.json": {
        "": "Use x,y or POINT(x y)",  # only for no lookup
    },
    "https://geojson.org/schema/Polygon.json": {"contains": "Use x,y or POINT(x y)"},
    "https://geojson.org/schema/MultiPolygon.json": {"contains": "Use x,y or POINT(x y)"},
}


def get_table_filter_params(table_schema: DatasetTableSchema) -> list[dict]:
    """Generate most OpenAPI query-string parameters for filtering.

    This will not include all possible nested relations,
    as that would explode in a huge combination.
    But it will suffice for most typical users.
    """
    openapi_params = []

    for field in table_schema.get_fields(include_subfields=False):
        if field.is_array_of_objects:
            # M2M relation or nested table.
            for sub_field in field.subfields:
                openapi_params.extend(_get_field_openapi_params(sub_field))
        else:
            # Flat direct field
            openapi_params.extend(_get_field_openapi_params(field))

    return openapi_params


def _get_field_openapi_params(field: DatasetFieldSchema, prefix="") -> list[dict]:  # noqa: C901
    """Generate the possible OpenAPI filter parameters for a single field."""
    if field.parent_field:
        prefix = f"{prefix}{field.parent_field.name}."

    openapi_params = []
    for lookup in QueryFilterEngine.get_allowed_lookups(field):
        param = {
            "name": _get_filter_name(prefix, field, lookup),
            "in": "query",
            "description": _get_filter_description(field, lookup=lookup),
            "schema": {},
        }

        if field.is_geo:
            param["schema"] = {"type": "string"}  # POINT(x y) or "x,y"
        elif type := OPENAPI_LOOKUP_TYPES.get(lookup):
            # Ignore field type, lookup has different type.
            param["schema"] = {"type": str(type)}
        else:
            # Use standard OpenAPI type/format like our JSONSchema also does.
            param["schema"] = {"type": field.type}
            if field.format:
                param["schema"]["format"] = field.format

            if field.is_array:
                param["schema"]["items"] = field["items"]  # expose all, is both JSONSchema.

            if lookup in OPENAPI_COMMA_LOOKUPS:
                # OpenAPI has a specific notation to encode "val1,val2,.." formats.
                # See: https://swagger.io/docs/specification/serialization/#query
                param["explode"] = False
                param["style"] = "form"
                param["schema"] = {"type": "array", "items": param["schema"]}

        if lookup in parser.MULTI_VALUE_LOOKUPS:
            # The 'field[not]=..' parameter can be repeated.
            param["schema"] = {
                "type": "array",
                "items": param["schema"],
            }

        openapi_params.append(param)

    return openapi_params


def _get_filter_name(prefix: str, field: DatasetFieldSchema, lookup: str) -> str:
    """Generate the filter name.
    This generates the "relation.field[lookup]" notation.
    """
    name = f"{prefix}{field.name}"
    if field.relation and not field.is_loose_relation:
        name += "Id"  # ForeignKey field
    if lookup:
        name = f"{name}[{lookup}]"
    return name


def _get_filter_description(field: DatasetFieldSchema, lookup=None) -> str | dict:  # noqa: C901
    """Generate a nice descriptive text for the filter.
    This is placed in the 'description' field instead of 'example',
    as the 'example' field will be pre-filled in Swagger.
    """
    if not lookup and field.description:
        return field.description

    try:
        # Generate example based on lookup.
        return OPENAPI_TYPE_LOOKUP_EXAMPLES[field.type][lookup]
    except KeyError:
        pass

    if description := OPENAPI_LOOKUP_EXAMPLES.get(lookup):
        return description

    if field.is_geo:
        return "GeoJSON | GEOMETRY(...)"
    elif field.relation:
        return "id"
    elif field.nm_relation:
        return "id"

    prefix = OPENAPI_LOOKUP_PREFIX.get(lookup, "")
    return prefix + OPENAPI_SCALAR_EXAMPLES[field.format or field.type]
