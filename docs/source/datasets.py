#!/usr/bin/env python
import os
import re
import sys
from pathlib import Path
from typing import Any, List, NamedTuple, Optional, Tuple, Union

import jinja2
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema
from schematools.utils import (
    dataset_paths_from_url,
    dataset_schema_from_file,
    dataset_schemas_from_url,
    to_snake_case,
    toCamelCase,
)

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
BASE_URL = "https://api.data.amsterdam.nl"

BASE_PATH = Path(__file__).parent.resolve()
TEMPLATE_PATH = BASE_PATH.joinpath("_templates")
TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath=TEMPLATE_PATH),
    autoescape=False,
)


class LookupContext(NamedTuple):
    operator: str
    value_example: Optional[str]
    description: str


re_camel_case = re.compile(
    r"(((?<=[^A-Z])[A-Z])|([A-Z](?![A-Z]))|((?<=[a-z])[0-9])|(?<=[0-9])[a-z])"
)
# This should match DEFAULT_LOOKUPS_BY_TYPE in DSO-API (except for the "exact" lookup)
_comparison_lookups = ["gt", "gte", "lt", "lte", "not", "isnull"]
_identifier_lookups = ["in", "not", "isnull"]
_polygon_lookups = ["contains", "isnull", "not"]
_string_lookups = ["like", "not", "isnull", "isempty"]
_number_lookups = _comparison_lookups + ["in"]

VALUE_EXAMPLES = {
    "string": ("Tekst", _string_lookups),
    "boolean": ("``true`` | ``false``", []),
    "integer": ("Geheel getal", _number_lookups),
    "number": ("Getal", _number_lookups),
    "time": ("``hh:mm[:ss[.ms]]``", _comparison_lookups),
    "date": ("``yyyy-mm-dd``", _comparison_lookups),
    "date-time": ("``yyyy-mm-dd`` of ``yyyy-mm-ddThh:mm[:ss[.ms]]``", _comparison_lookups),
    "uri": ("https://....", _string_lookups),
    "array": ("value,value", ["contains"]),  # comma separated list of strings
    "https://geojson.org/schema/Polygon.json": (
        "GeoJSON of ``POLYGON(x y ...)``",
        _polygon_lookups,
    ),
    "https://geojson.org/schema/MultiPolygon.json": (
        "GeoJSON of ``MULTIPOLYGON(x y ...)``",
        _polygon_lookups,
    ),
}

LOOKUP_CONTEXT = {
    lookup.operator: lookup
    for lookup in [
        LookupContext("gt", None, "Test op groter dan (``>``)."),
        LookupContext("gte", None, "Test op groter dan of gelijk (``>=``)."),
        LookupContext("lt", None, "Test op kleiner dan (``<``)."),
        LookupContext("lte", None, "Test op kleiner dan of gelijk (``<=``)."),
        LookupContext(
            "like", "Tekst met jokertekens (``*`` en ``?``).", "Test op gedeelte van tekst."
        ),
        LookupContext(
            "in",
            "Lijst van waarden",
            "Test of de waarde overeenkomst met 1 van de opties (``IN``).",
        ),
        LookupContext("not", None, "Test of waarde niet overeenkomt (``!=``)."),
        LookupContext(
            "contains", "Comma gescheiden lijst", "Test of er een intersectie is met de waarde."
        ),
        LookupContext(
            "isnull",
            "``true`` of ``false``",
            "Test op ontbrekende waarden (``IS NULL`` / ``IS NOT NULL``).",
        ),
        LookupContext(
            "isempty", "``true`` of ``false``", "Test of de waarde leeg is (``== ''`` / ``!= ''``)"
        ),
    ]
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


def render_dataset_docs(dataset: DatasetSchema, paths: dict[str, str]):
    snake_name = to_snake_case(dataset.id)
    dataset_path = paths[dataset.id]
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_table_context(t, paths) for t in dataset.tables]
    if any(t["has_geometry"] for t in tables):
        wfs_url = f"{BASE_URL}/v1/wfs/{dataset_path}/"
    else:
        wfs_url = None

    render_template(
        "datasets/dataset.rst.j2",
        f"datasets/{dataset_path}.rst",
        {
            "schema": dataset,
            "schema_name": snake_name,
            "schema_auth": dataset.auth,
            "main_title": main_title,
            "tables": tables,
            "wfs_url": wfs_url,
            "swagger_url": f"{BASE_URL}/v1/{dataset_path}/",
        },
    )

    return dataset_path


def render_wfs_dataset_docs(dataset: DatasetSchema, paths: dict[str, str]):
    """Render the docs for the WFS dataset."""
    snake_name = to_snake_case(dataset.id)
    dataset_path = paths[dataset.id]
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_feature_type_context(t, paths) for t in dataset.tables]
    if all(not t["has_geometry"] for t in tables):
        return None

    render_template(
        "wfs-datasets/dataset.rst.j2",
        f"wfs-datasets/{dataset_path}.rst",
        {
            "schema": dataset,
            "schema_name": snake_name,
            "main_title": main_title,
            "tables": tables,
            "wfs_url": f"{BASE_URL}/v1/wfs/{dataset_path}/",
        },
    )

    return dataset_path


def _get_table_context(table: DatasetTableSchema, paths: dict[str, str]):
    """Collect all table data for the REST API spec."""
    uri = _get_table_uri(table, paths)
    fields = _get_fields(table.fields, table_identifier=table.identifier)

    return {
        "title": to_snake_case(table.id).replace("_", " ").capitalize(),
        "doc_id": f"{table.dataset.id}:{table.id}",
        "uri": uri,
        "rest_csv": f"{uri}?_format=csv",
        "rest_geojson": f"{uri}?_format=geojson",
        "description": table.get("description"),
        "fields": [_get_field_context(field, table.identifier) for field in fields],
        "auth": table.auth | table.dataset.auth,
        "expands": _get_table_expands(table),
        "additional_filters": table.additional_filters,
        "source": table,
        "has_geometry": _has_geometry(table),
    }


def _get_table_uri(table: DatasetTableSchema, paths: dict[str, str]) -> str:
    """Tell where the endpoint of a table will be"""
    dataset_path = paths[table.dataset.id]
    snake_id = to_snake_case(table.id)
    return f"{BASE_URL}/v1/{dataset_path}/{snake_id}/"


def _get_table_expands(table: DatasetTableSchema, rel_id_separator=":"):
    """Return which relations can be expanded"""
    expands = [
        {
            "id": field.id,
            "camel_name": toCamelCase(field.id),
            "snake_name": to_snake_case(field.id),
            "relation_id": field["relation"].replace(":", rel_id_separator),
            "target_doc_id": field["relation"].replace(":", rel_id_separator),
            "related_table": field.related_table,
        }
        for field in table.get_fields(include_sub_fields=False)
        if field.get("relation") is not None
    ]

    # Reverse relations can also be expanded
    for additional_relation in table.additional_relations:
        related_table = additional_relation.related_table
        expands.append(
            {
                "id": additional_relation.id,
                "camel_name": toCamelCase(additional_relation.id),
                "snake_name": to_snake_case(additional_relation.id),
                "relation_id": additional_relation.relation.replace(":", rel_id_separator),
                "target_doc_id": f"{related_table.dataset.id}{rel_id_separator}{related_table.id}",
                "related_table": related_table,
            }
        )

    return sorted(expands, key=lambda item: item["id"])


def _has_geometry(table: DatasetTableSchema) -> bool:
    """Tell whether a table has a geometry"""
    return any(
        f.get("$ref", "").startswith("https://geojson.org/schema/")
        for f in table["schema"]["properties"].values()
    )


def _get_feature_type_context(table: DatasetTableSchema, paths: dict[str, str]):
    """Collect all table data for the WFS server spec."""
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table["id"])
    parent_path = paths[table.dataset.id]
    uri = f"{BASE_URL}/v1/wfs/{parent_path}/{snake_id}/"

    fields = _get_fields(table.fields, table_identifier=table.identifier)
    has_geometry = _has_geometry(table)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "typenames": [f"app:{snake_id}", snake_id],
        "doc_id": f"{table.dataset.id}/{table.id}",
        "uri": uri,
        "description": table.get("description"),
        "fields": [_get_field_context(field, table.identifier) for field in fields],
        "auth": table.auth,
        "expands": _get_table_expands(table, rel_id_separator="/"),
        "source": table,
        "has_geometry": has_geometry,
        "wfs_typename": f"app:{snake_name}",
        "wfs_csv": (
            f"{uri}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            f"&TYPENAMES={snake_id}&OUTPUTFORMAT=csv"
            if has_geometry
            else ""
        ),
        "wfs_geojson": (
            f"{uri}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            f"&TYPENAMES={snake_id}&OUTPUTFORMAT=geojson"
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


def _get_field_context(field: DatasetFieldSchema, identifier: List[str]) -> dict[str, Any]:
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
        value_example = f"GeoJSON of ``{type.upper()}(x y ...)``"
        lookups = []
    elif field.relation or "://" in type:
        lookups = _identifier_lookups

    return {
        "name": field.name,
        "snake_name": snake_name,
        "camel_name": camel_name,
        "is_identifier": field.name in identifier,
        "type": (type or "").capitalize(),
        "value_example": value_example or "",
        "description": field.description or "",
        "lookups": [LOOKUP_CONTEXT[op] for op in lookups],
        "source": field,
        "auth": field.auth | field.table.auth | field.table.dataset.auth,
    }


def render_datasets(*local_file_paths):
    if not local_file_paths:
        print(f"fetching definitions from {SCHEMA_URL}")
        schemas = dataset_schemas_from_url(SCHEMA_URL)
        paths = dataset_paths_from_url(SCHEMA_URL)
    else:
        print("fetching datasets from local folders")
        schemas = {}
        paths = {}
        for file_path in local_file_paths:
            file_path = os.path.abspath(file_path)
            if (pos := file_path.find("/datasets/")) == -1:
                raise ValueError(
                    f"The provided dataset ({file_path}) should exist in a `datasets` folder."
                )

            ds_path = file_path[pos + 10 : file_path.rfind("/")]
            print(f"- reading {ds_path}")
            schema = dataset_schema_from_file(file_path, prefetch_related=True)
            schemas[schema.id] = schema
            paths[schema.id] = ds_path

    documents = []
    for name, dataset in sort_schemas(schemas.items()):
        documents.append(render_dataset_docs(dataset, paths))

    render_template("datasets/index.rst.j2", "datasets/index.rst", {"documents": documents})

    wfs_documents = []
    for name, dataset in sort_schemas(schemas.items()):
        name = render_wfs_dataset_docs(dataset, paths)
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
    try:
        output_file.parent.mkdir(parents=True)
    except FileExistsError:
        pass
    output_file.write_text(template.render(**context_data))


def underline(text, symbol):
    return "{text}\n{underline}".format(text=text.capitalize(), underline=symbol * len(text))


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
    # Allow passing local filenames for debugging
    render_datasets(*sys.argv[1:])
