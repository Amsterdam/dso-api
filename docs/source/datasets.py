#!/usr/bin/env python
from typing import List, Tuple

import os
import re
from pathlib import Path

import jinja2
from string_utils import slugify
from schematools.types import DatasetSchema, DatasetTableSchema
from schematools.utils import schema_defs_from_url

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")

BASE_PATH = Path("./source/")
TEMPLATE_PATH = BASE_PATH.joinpath("_templates")
TEMPLATE_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath=TEMPLATE_PATH), autoescape=False,
)

re_camel_case = re.compile(
    r"(((?<=[^A-Z])[A-Z])|([A-Z](?![A-Z]))|((?<=[a-z])[0-9])|(?<=[0-9])[a-z])"
)
_comparison_lookups = ["gt", "gte", "lt", "lte", "not", "isnull"]
_integer_lookups = _comparison_lookups + ["in"]
_array_lookups = ["contains"]  # comma separated list of strings
_identifier_lookups = [
    "in",
    "not",
    "isnull",
]
VALUE_EXAMPLES = {
    "string": "Tekst met wildcard",
    "boolean": "``true`` | ``false``",
    "integer": "Geheel getal",
    "number": "Getal",
    "time": "``hh:mm[:ss[.ms]]``",
    "date": "``yyyy-mm-dd`` or ``yyyy-mm-ddThh:mm[:ss[.ms]]``",
}


def render_dataset_docs(dataset: DatasetSchema):
    snake_name = to_snake_case(dataset["id"])

    render_template(
        "datasets/dataset.rst.j2",
        f"datasets/{snake_name}.rst",
        {
            "schema": dataset,
            "main_title": dataset.get("title")
            or snake_name.replace("_", " ").capitalize(),
            "tables": [_get_table_context(t) for t in dataset.tables],
        },
    )

    return snake_name


def _get_table_context(table: DatasetTableSchema):
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table["id"])
    uri = f"/v1/{snake_name}/{snake_id}/"

    fields = _get_fields(table["schema"]["properties"])

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "uri": uri,
        "fields": [_get_field_context(field_id, field) for field_id, field in fields],
        "relations": [
            {"name": toCamelCase(relation_name), "relation": field["relation"]}
            for relation_name, field in table["schema"]["properties"].items()
            if field.get("relation") is not None
        ],
        "additional_filters": table.filters,
        "additional_relations": table.relations,
        "source": table,
    }


def _get_fields(properties, prefix=None) -> List[Tuple[str, dict]]:
    """Flatten a nested listing of fields."""
    fields = []
    for field_id, field in properties.items():
        if field_id == "schema":
            continue

        fields.append((f"{prefix}.{field_id}" if prefix else field_id, field))

        type = field.get("type")
        if type == "array":
            items = field.get("items")
            if items and items.get("type") == "object":
                fields.extend(_get_fields(items["properties"], prefix=field_id))
        elif type == "object":
            fields.extend(_get_fields(field["properties"], prefix=field_id))

    return fields


def _get_field_context(field_id, field: dict):
    """Get context data for a field."""
    type = field.get("type")
    value_example = VALUE_EXAMPLES.get(type)
    ref = field.get("$ref")
    if ref:
        if ref.startswith("https://geojson.org/schema/"):
            type = ref[27:-5]
            value_example = f"GeoJSON | {type.upper()}(x y ...)"
            lookups = []
        else:
            lookups = _identifier_lookups
    else:
        if type in ("number", "integer"):
            lookups = _integer_lookups
        elif type == "array":
            lookups = _array_lookups
        else:
            lookups = _comparison_lookups

    return {
        "name": toCamelCase(field_id),
        "type": (type or "").capitalize(),
        "value_example": value_example or "",
        "description": field.get("description", ""),
        "lookups": lookups,
        "source": field,
    }


def render_datasets():
    documents = []
    for name, dataset in schema_defs_from_url(SCHEMA_URL).items():
        documents.append(render_dataset_docs(dataset))

    render_template(
        "datasets/index.rst.j2", "datasets/index.rst", {"documents": documents}
    )


# ---------- INTERNAL ---


def render_template(template_name, output_file, context_data: dict):
    """Render a Jinja2 template"""
    template = TEMPLATE_ENV.get_template(template_name)

    output_file = BASE_PATH.joinpath(output_file)
    output_file.write_text(template.render(**context_data))


def underline(text, symbol):
    return "{text}\n{underline}".format(
        text=text.capitalize(), underline=symbol * len(text)
    )


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


TEMPLATE_ENV.filters["to_snake_case"] = to_snake_case
TEMPLATE_ENV.filters["toCamelCase"] = toCamelCase
TEMPLATE_ENV.filters["underline"] = underline

if __name__ == "__main__":
    render_datasets()
