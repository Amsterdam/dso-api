#!/usr/bin/env python
import os
import sys
from pathlib import Path
from typing import Any, FrozenSet, List, NamedTuple, Optional

import jinja2
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema
from schematools.utils import (
    dataset_schemas_from_schemas_path,
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
    autoescape=True,
)


class LookupContext(NamedTuple):
    operator: str
    value_example: Optional[str]
    description: str


# This should match ALLOWED_SCALAR_LOOKUPS in DSO-API (except for the "exact" lookup)
_comparison_lookups = ["gt", "gte", "lt", "lte", "not", "in", "isnull"]
_identifier_lookups = ["in", "not", "isnull"]
_polygon_lookups = ["contains", "isnull", "not"]
_string_lookups = ["in", "like", "not", "isnull", "isempty"]

FORMAT_ALIASES = {
    "date-time": "Datetime",
}

VALUE_EXAMPLES = {
    "string": ("Tekst", _string_lookups),
    "boolean": ("``true`` | ``false``", []),
    "integer": ("Geheel getal", _comparison_lookups),
    "number": ("Getal", _comparison_lookups),
    "time": ("``hh:mm[:ss[.ms]]``", _comparison_lookups),
    "date": ("``yyyy-mm-dd``", _comparison_lookups),
    "date-time": ("``yyyy-mm-dd`` of ``yyyy-mm-ddThh:mm[:ss[.ms]]``", _comparison_lookups),
    "uri": ("https://....", _string_lookups),
    "array": ("value,value", ["contains"]),  # comma separated list of strings
    "https://geojson.org/schema/Geometry.json": ("geometry", _polygon_lookups),
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


def render_dataset_docs(dataset: DatasetSchema, dataset_path: str):
    snake_name = to_snake_case(dataset.id)
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_table_context(t, dataset_path) for t in dataset.tables]
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
            "schema_auth": _fix_auth(dataset.auth),
            "dataset_has_auth": len(_fix_auth(dataset.auth))
            or len([table for table in tables if table.get("auth")]),
            "main_title": main_title,
            "tables": tables,
            "wfs_url": wfs_url,
            "swagger_url": f"{BASE_URL}/v1/{dataset_path}/",
        },
    )

    return dataset_path


def render_wfs_dataset_docs(dataset: DatasetSchema, dataset_path: str):
    """Render the docs for the WFS dataset."""
    snake_name = to_snake_case(dataset.id)
    main_title = dataset.title or snake_name.replace("_", " ").capitalize()
    tables = [_get_feature_type_context(t, dataset_path) for t in dataset.tables]
    if all(not t["has_geometry"] for t in tables):
        return None

    render_template(
        "wfs-datasets/dataset.rst.j2",
        f"wfs-datasets/{dataset_path}.rst",
        {
            "schema": dataset,
            "schema_name": snake_name,
            "schema_auth": _fix_auth(dataset.auth),
            "main_title": main_title,
            "tables": tables,
            "wfs_url": f"{BASE_URL}/v1/wfs/{dataset_path}/",
        },
    )

    return dataset_path


def _get_table_context(table: DatasetTableSchema, paths: dict[str, str]):
    """Collect all table data for the REST API spec."""
    uri = _get_table_uri(table, paths)
    table_fields = list(table.get_fields(include_subfields=False))
    fields = _get_fields(table_fields)
    filters = _get_filters(table_fields)

    return {
        "title": to_snake_case(table.id).replace("_", " ").capitalize(),
        "doc_id": f"{table.dataset.id}:{table.id}",
        "uri": uri,
        "rest_csv": f"{uri}?_format=csv",
        "rest_geojson": f"{uri}?_format=geojson",
        "description": table.get("description"),
        "fields": [_get_field_context(field) for field in fields],
        "filters": filters,
        "auth": _fix_auth(table.auth | table.dataset.auth),
        "expands": _get_table_expands(table),
        "source": table,
        "has_geometry": _has_geometry(table),
    }


def _get_table_uri(table: DatasetTableSchema, path: str) -> str:
    """Tell where the endpoint of a table will be"""
    snake_id = to_snake_case(table.id)
    return f"{BASE_URL}/v1/{path}/{snake_id}/"


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
        for field in table.get_fields(include_subfields=False)
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


def _get_feature_type_context(table: DatasetTableSchema, parent_path: str):
    """Collect all table data for the WFS server spec."""
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table["id"])
    uri = f"{BASE_URL}/v1/wfs/{parent_path}/"

    fields = _get_fields(table.fields)
    has_geometry = _has_geometry(table)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "typenames": [f"app:{snake_id}", snake_id],
        "doc_id": f"{table.dataset.id}/{table.id}",
        "uri": uri,
        "description": table.get("description"),
        "fields": [_get_field_context(field) for field in fields],
        "auth": _fix_auth(table.dataset.auth | table.auth),
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


def _get_fields(table_fields) -> List[DatasetFieldSchema]:
    """Flatten a nested listing of fields."""
    result_fields = []
    for field in table_fields:
        if field.name == "schema":
            continue

        result_fields.append(field)
        result_fields.extend(_get_fields(field.subfields))

    return result_fields


def _field_data(field: DatasetFieldSchema):
    type = field.type
    format = field.format
    try:
        value_example, lookups = VALUE_EXAMPLES[format or type]
    except KeyError:
        value_example = ""
        lookups = []

    if format:
        # A string field with a format (e.g. date-time).
        return FORMAT_ALIASES.get(format, format), value_example, lookups

    # This closely mimics what the Django filter+serializer logic does
    if type.startswith("https://geojson.org/schema/"):
        # Catch-all for other geometry types
        type = type[27:-5]
        value_example = f"GeoJSON of ``{type.upper()}(x y ...)``"
        lookups = []
    elif field.relation or "://" in type:
        lookups = _identifier_lookups
        if field.type == "string":
            lookups += [lookup for lookup in _string_lookups if lookup not in lookups]

    return type, value_example, lookups


def _get_field_context(field: DatasetFieldSchema) -> dict[str, Any]:
    """Get context data for a field."""
    identifiers = field.table.identifier
    is_deprecated = False

    snake_name = _get_field_snake_name(field)
    camel_name = _get_field_camel_name(field)

    if field.relation:
        # Mimic Django ForeignKey _id suffix.
        snake_name += "_id"
        camel_name += "Id"
        is_deprecated = True

    type, value_example, _ = _field_data(field)
    description = field.description
    is_foreign_id = field.parent_field is not None and field.name in identifiers
    if not description and is_foreign_id and field.name == identifiers[0]:
        # First identifier gets parent field description.
        description = field.parent_field.description

    return {
        "name": field.name,
        "snake_name": snake_name,
        "camel_name": camel_name,
        "is_identifier": field.name in identifiers,
        "is_deprecated": is_deprecated,
        "is_relation": bool(field.relation),
        "is_foreign_id": is_foreign_id,
        "type": (type or "").capitalize(),
        "description": description or "",
        "source": field,
        "auth": _fix_auth(field.auth | field.table.auth | field.table.dataset.auth),
    }


def _get_field_snake_name(field: DatasetFieldSchema) -> str:
    """Find the snake and camel names of a field"""
    snake_name = to_snake_case(field.name)

    parent_field = field.parent_field
    while parent_field is not None:
        parent_snake_name = to_snake_case(parent_field.name)
        snake_name = f"{parent_snake_name}.{snake_name}"
        parent_field = parent_field.parent_field

    return snake_name


def _get_field_camel_name(field: DatasetFieldSchema) -> str:
    """Find the snake and camel names of a field"""
    camel_name = toCamelCase(field.name)
    parent_field = field.parent_field
    while parent_field is not None:
        parent_camel_name = toCamelCase(parent_field.name)
        camel_name = f"{parent_camel_name}.{camel_name}"
        parent_field = parent_field.parent_field

    return camel_name


def _get_filters(table_fields: List[DatasetFieldSchema]) -> List[dict[str, Any]]:
    filters = []
    id_seen = False
    for field in table_fields:
        if field.id == "schema":
            continue
        # temporary patch until schematools is bumped to a version that
        # does not duplicate the id field
        if field.id == "id" and id_seen:
            continue
        if field.id == "id":
            id_seen = True
        filters.extend(_get_filter_context(field))
    return filters


def _filter_payload(
    field: DatasetFieldSchema, *, prefix: str = "", name_suffix: str = "", is_deprecated=False
):
    name = prefix + _get_field_camel_name(field) + name_suffix
    type, value_example, lookups = _field_data(field)

    return {
        "name": name,
        "type": type.capitalize(),
        "is_deprecated": is_deprecated,
        "value_example": value_example or "",
        "lookups": [LOOKUP_CONTEXT[op] for op in lookups],
        "auth": _fix_auth(field.auth | field.table.auth | field.table.dataset.auth),
    }


def _get_filter_context(field: DatasetFieldSchema) -> List[dict[str, Any]]:
    """Return zero or more filter context(s) from the a field schema.

    This function essentially reconstructs the output of the FilterSet
    generation in the dynamic api directly from the underlying schema.
    """
    if field.relation:
        if field.is_scalar:
            # normal FKs, can now be parsed using dot-notation
            prefix = _get_field_camel_name(field) + "."
            result = [
                _filter_payload(field.related_table.get_field_by_id(id_field), prefix=prefix)
                for id_field in field.related_table.identifier
            ]
            # Also include the old notation, that still works too (but deprecated)
            return result + [_filter_payload(field, name_suffix="Id", is_deprecated=True)]
        elif field.is_object:
            # composite key / temporal relation. Add those fields
            related_identifiers = field.related_table.identifier
            result = [
                _filter_payload(sub_field)
                for sub_field in field.subfields
                if sub_field.id in related_identifiers
            ]

            # Our implementation still inclues a regular foreign key,
            # since Django doesn't support composite pks - used more in the past (but deprecated).
            return result + [_filter_payload(field, name_suffix="Id", is_deprecated=True)]
    elif field.is_nested_table:
        return [_filter_payload(f) for f in field.subfields]
    elif field.is_scalar or field.is_array_of_scalars:
        # Regular filters
        return [_filter_payload(field)]
    elif field.nm_relation:
        return [_filter_payload(field)]

    # TODO: Field is an object but not a relation?

    return []


def _fix_auth(auth: FrozenSet[str]) -> FrozenSet[str]:
    """Hide the OPENBAAR tag.
    When the dataset is public, but table isn't,
    this could even mix authorization levels.
    """
    return auth - {"OPENBAAR"}


def _dataset_name(name):
    return name.replace(".rst", "")


def _documents(dir_names, file_names):
    """Filter a set of dir and filenames as given by os.walk
    to be included in a dataset directory toc tree"""
    return sorted(
        [f"{dir_name}/index" for dir_name in dir_names]
        + [_dataset_name(fname) for fname in file_names if fname != "index.rst"]
    )


def render_datasets(schema_dir):
    if schema_dir is not None:
        print(f"fetching datasets from local folder {schema_dir}")
        schemas = dataset_schemas_from_schemas_path(schema_dir)
    else:
        print(f"fetching definitions from {SCHEMA_URL}")
        schemas = dataset_schemas_from_url(SCHEMA_URL)

    datasets_path = BASE_PATH / Path("datasets")

    for path, dataset in schemas.items():
        render_dataset_docs(dataset, path)

    # Leverage the fact that the dataset rendering has written the same
    # directory structure as the remote datasets listing in order
    # to generate subpaths in the TOC-tree.
    dir_tree = os.walk(datasets_path, topdown=True)
    _, root_dirs, root_files = next(dir_tree)

    # Add a sub TOC-tree to all sub-directories
    for dir_path, dir_names, file_names in dir_tree:
        node_title = dir_path.split("/")[-1].title()
        render_template(
            "datasets/sub-index.rst.j2",
            f"{dir_path}/index.rst",
            {
                "documents": _documents(dir_names, file_names),
                "node_title": node_title,
                "section_marker": "-" * len(node_title),
            },
        )

    # Add the root TOC-tree
    render_template(
        "datasets/index.rst.j2",
        "datasets/index.rst",
        {"documents": _documents(root_dirs, root_files)},
    )

    for path, dataset in schemas.items():
        render_wfs_dataset_docs(dataset, path)

    datasets_path = BASE_PATH / Path("wfs-datasets")

    dir_tree = os.walk(datasets_path, topdown=True)
    _, root_dirs, root_files = next(dir_tree)

    # Add a sub TOC-tree to all sub-directories
    for dir_path, dir_names, file_names in dir_tree:
        node_title = dir_path.split("/")[-1].title()
        render_template(
            "wfs-datasets/sub-index.rst.j2",
            f"{dir_path}/index.rst",
            {
                "documents": _documents(dir_names, file_names),
                "node_title": node_title,
                "section_marker": "-" * len(node_title),
            },
        )

    # Add the root TOC-tree
    render_template(
        "wfs-datasets/index.rst.j2",
        "wfs-datasets/index.rst",
        {"documents": _documents(root_dirs, root_files)},
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
    path = None
    if len(sys.argv) > 1:
        path = sys.argv[1]
    render_datasets(path)
