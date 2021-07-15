#!/usr/bin/env python
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import jinja2
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema
from schematools.utils import schema_defs_from_url
from string_utils import slugify

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
BASE_URL = "https://api.data.amsterdam.nl"

BASE_PATH = Path("./source/")
TEMPLATE_PATH = BASE_PATH.joinpath("_templates")
TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath=TEMPLATE_PATH),
    autoescape=False,
)

re_camel_case = re.compile(
    r"(((?<=[^A-Z])[A-Z])|([A-Z](?![A-Z]))|((?<=[a-z])[0-9])|(?<=[0-9])[a-z])"
)
# This should match DEFAULT_LOOKUPS_BY_TYPE in DSO-API (except for the "exact" lookup)
_comparison_lookups = ["gte", "gt", "lt", "lte", "not", "isnull"]
_identifier_lookups = ["in", "not", "isnull"]
_polygon_lookups = ["contains", "isnull", "not"]
_string_lookups = ["isnull", "not", "isempty", "like"]
_number_lookups = _comparison_lookups + ["in"]
VALUE_EXAMPLES = {
    "string": ("Tekst exacte match", _string_lookups),
    "boolean": ("``true`` | ``false``", []),
    "integer": ("Geheel getal", _number_lookups),
    "number": ("Getal", _number_lookups),
    "time": ("``hh:mm[:ss[.ms]]``", _comparison_lookups),
    "date": ("``yyyy-mm-dd``", _comparison_lookups),
    "date-time": ("``yyyy-mm-dd`` or ``yyyy-mm-ddThh:mm[:ss[.ms]]``", _comparison_lookups),
    "uri": ("https://....", _string_lookups),
    "array": ("value,value", ["contains"]),  # comma separated list of strings
    "https://geojson.org/schema/Polygon.json": ("GeoJSON | POLYGON(x y ...)", _polygon_lookups),
    "https://geojson.org/schema/MultiPolygon.json": (
        "GeoJSON | MULTIPOLYGON(x y ...)",
        _polygon_lookups,
    ),
}


def sort_schemas(schemas: List[Tuple[str, DatasetSchema]]) -> List[Union[str, DatasetSchema]]:
    """Sort datasets (schemas) alphabetically.

    Args:
        schemas: A list of tuples containing a pair of schemas id (name) and
            DatasetSchema instance.

    Returns:
        A list of alphabetically ordered schemas instances based on their schema id (name).
    """
    return sorted(schemas, key=lambda schema: schema[0])


def sort_tables(tables: List[DatasetTableSchema]) -> List[DatasetTableSchema]:
    """Sort tables alphabetically.

    Args:
        tables: A list of DatasetTableSchema instances

    Returns:
        A list of DatasetTableSchema instances ordered based on table id (equals name).
    """
    return sorted(tables, key=lambda table: table.id)


def sort_fields(
    fields: List[DatasetFieldSchema], table_identifier: Optional[List[str]]
) -> List[DatasetFieldSchema]:
    """Sort fields of an table alphabetically.
    Put the identifier field(s) always first, after that, fields are
    alphabetically ordered based on field name.

    Args:
        fields: A list of DatasetFieldSchema instances.
        table_identifier: If present, the table identifier(s) field(s) are placed
            first in the output.

    Returns:
        A list of DatasetFieldSchema instances ordered based on field name,
            and places identifier fields first if exists.
    """
    sorted_fields = []

    if table_identifier:

        fields_to_sort = [field for field in fields if field.name not in table_identifier]
        sorted_fields = sorted(fields_to_sort, key=lambda field: field.name)
        identifier_fields = [
            field for field in fields if table_identifier and field.name in table_identifier
        ]
        for field in identifier_fields:
            sorted_fields.insert(0, field)
    else:
        sorted_fields = sorted([field for field in fields], key=lambda field: field.name)

    return sorted_fields


def render_dataset_docs(dataset: DatasetSchema):
    snake_name = to_snake_case(dataset.id)
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_table_context(t) for t in dataset.tables]
    if any(t["has_geometry"] for t in tables):
        wfs_url = f"{BASE_URL}/v1/wfs/{snake_name}/"
    else:
        wfs_url = None

    render_template(
        "datasets/dataset.rst.j2",
        f"datasets/{snake_name}.rst",
        {
            "schema": dataset,
            "schema_name": snake_name,
            "schema_auth": dataset.auth,
            "main_title": main_title,
            "tables": tables,
            "wfs_url": wfs_url,
            "swagger_url": f"{BASE_URL}/v1/{dataset.id}/",
        },
    )

    return snake_name


def render_wfs_dataset_docs(dataset: DatasetSchema):
    """Render the docs for the WFS dataset."""
    snake_name = to_snake_case(dataset.id)
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_feature_type_context(t) for t in dataset.tables]
    if all(not t["has_geometry"] for t in tables):
        return None

    embeds = {}
    for table in tables:
        for embed in table["embeds"]:
            embeds[embed["id"]] = embed

    render_template(
        "wfs-datasets/dataset.rst.j2",
        f"wfs-datasets/{snake_name}.rst",
        {
            "schema": dataset,
            "schema_name": snake_name,
            "main_title": main_title,
            "tables": tables,
            "embeds": sorted(embeds.values(), key=lambda e: e["id"]),
            "wfs_url": f"{BASE_URL}/v1/wfs/{snake_name}/",
        },
    )

    return snake_name


def _get_table_context(table: DatasetTableSchema):
    """Collect all table data for the REST API spec."""
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table["id"])
    uri = f"{BASE_URL}/v1/{snake_name}/{snake_id}/"

    fields = _get_fields(table.fields, table_identifier=table.identifier)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "uri": uri,
        "rest_csv": f"{uri}?_format=csv",
        "rest_geojson": f"{uri}?_format=geojson",
        "description": table.get("description"),
        "fields": [_get_field_context(field, table.identifier) for field in fields],
        "auth": table.auth,
        "relations": [
            {
                "id": relation_name,
                "camel_name": toCamelCase(relation_name),
                "relation": field["relation"],
            }
            for relation_name, field in table["schema"]["properties"].items()
            if field.get("relation") is not None
        ],
        "additional_filters": table.filters,
        "additional_relations": table.relations,
        "source": table,
        "has_geometry": _has_geometry(table),
    }


def _has_geometry(table: DatasetTableSchema) -> bool:
    """Tell whether a table has a geometry"""
    return any(
        f.get("$ref", "").startswith("https://geojson.org/schema/")
        for f in table["schema"]["properties"].values()
    )


def _get_feature_type_context(table: DatasetTableSchema):
    """Collect all table data for the WFS server spec."""
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table["id"])
    uri = f"{BASE_URL}/v1/{snake_name}/{snake_id}/"

    fields = _get_fields(table.fields, table_identifier=table.identifier)
    has_geometry = _has_geometry(table)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "typenames": [f"app:{snake_id}", snake_id],
        "uri": uri,
        "description": table.get("description"),
        "fields": [_get_field_context(field, table.identifier) for field in fields],
        "auth": table.auth,
        "embeds": [
            {
                "id": relation_name,
                "snake_name": to_snake_case(relation_name),
            }
            for relation_name, field in table["schema"]["properties"].items()
            if field.get("relation") is not None
        ],
        "source": table,
        "has_geometry": has_geometry,
        "wfs_typename": f"app:{snake_name}",
        "wfs_csv": (
            f"{BASE_URL}/v1/wfs/{snake_name}/?SERVICE=WFS&VERSION=2.0.0"
            f"&REQUEST=GetFeature&TYPENAMES={snake_id}&OUTPUTFORMAT=csv"
            if has_geometry
            else ""
        ),
        "wfs_geojson": (
            f"{BASE_URL}/v1/wfs/{snake_name}/?SERVICE=WFS&VERSION=2.0.0"
            f"&REQUEST=GetFeature&TYPENAMES={snake_id}&OUTPUTFORMAT=geojson"
            if has_geometry
            else ""
        ),
    }


def _get_fields(
    table_fields, table_identifier=None, parent_field=None
) -> List[DatasetFieldSchema]:
    """Flatten a nested listing of fields."""
    result_fields = []
    for field in table_fields:
        if field.name == "schema":
            continue

        result_fields.append(field)

        if field.is_array_of_objects or field.is_object:
            result_fields.extend(_get_fields(field.sub_fields, parent_field=field))

    return result_fields


def _get_field_context(field: DatasetFieldSchema, identifier: List[str]) -> Dict[str, Any]:
    """Get context data for a field."""
    type = field.type
    format = field.format
    try:
        value_example, lookups = VALUE_EXAMPLES[format or type]
    except KeyError:
        value_example = ""
        lookups = []

    snake_name = to_snake_case(field.name)
    camel_name = toCamelCase(field.name)

    if field.relation:
        # Mimic Django ForeignKey _id suffix.
        snake_name += "_id"
        camel_name += "Id"

    parent_field = field.parent_field
    while parent_field is not None:
        parent_snake_name = to_snake_case(parent_field.name)
        parent_camel_name = toCamelCase(parent_field.name)
        snake_name = f"{parent_snake_name}.{snake_name}"
        camel_name = f"{parent_camel_name}.{camel_name}"
        parent_field = parent_field.parent_field

    # This closely mimics what the Django filter+serializer logic does
    if type.startswith("https://geojson.org/schema/"):
        # Catch-all for other geometry types
        type = type[27:-5]
        value_example = f"GeoJSON | {type.upper()}(x y ...)"
        lookups = []
    elif field.relation or "://" in type:
        lookups = _identifier_lookups

    return {
        "name": field.name,
        "snake_name": snake_name,
        "camel_name": f"{camel_name} (identificatie)" if field.name in identifier else camel_name,
        "type": (type or "").capitalize(),
        "value_example": value_example or "",
        "description": field.description,
        "lookups": sorted(lookups),
        "source": field,
        "auth": field.auth,
    }


def render_datasets():
    print(f"fetching definitions from {SCHEMA_URL}")
    schemas = schema_defs_from_url(SCHEMA_URL)

    documents = []
    for name, dataset in sort_schemas(schemas.items()):
        documents.append(render_dataset_docs(dataset))

    render_template("datasets/index.rst.j2", "datasets/index.rst", {"documents": documents})

    wfs_documents = []
    for name, dataset in sort_schemas(schemas.items()):
        name = render_wfs_dataset_docs(dataset)
        if name:
            wfs_documents.append(name)

    render_template(
        "wfs-datasets/index.rst.j2",
        "wfs-datasets/index.rst",
        {"documents": wfs_documents},
    )


# ---------- INTERNAL ---


def render_template(template_name, output_file, context_data: dict):
    """Render a Jinja2 template"""
    template = TEMPLATE_ENV.get_template(template_name)

    print(f"writing {output_file}")
    output_file = BASE_PATH.joinpath(output_file)
    output_file.write_text(template.render(**context_data))


def underline(text, symbol):
    return "{text}\n{underline}".format(text=text.capitalize(), underline=symbol * len(text))


def toCamelCase(name):
    """
    Unify field/column/dataset name from Space separated/Snake Case/Camel case
    to camelCase.
    """
    name = " ".join(name.split("_"))
    words = re_camel_case.sub(r" \1", name).strip().lower().split(" ")
    return "".join(w.lower() if i == 0 else w.title() for i, w in enumerate(words))


def to_snake_case(name):
    """
    Convert field/column/dataset name from Space separated/Snake Case/Camel case
    to snake_case.
    """
    # Convert to field name, avoiding snake_case to snake_case issues.
    name = toCamelCase(name)
    return slugify(re_camel_case.sub(r" \1", name).strip().lower(), separator="_")


def strip_base_url(url):
    if url.startswith(BASE_URL):
        return url[len(BASE_URL) :]
    else:
        return url


TEMPLATE_ENV.filters["to_snake_case"] = to_snake_case
TEMPLATE_ENV.filters["toCamelCase"] = toCamelCase
TEMPLATE_ENV.filters["underline"] = underline
TEMPLATE_ENV.filters["strip_base_url"] = strip_base_url

if __name__ == "__main__":
    render_datasets()
