"""Dataset documentation views."""
from typing import Any, List, FrozenSet, Optional, NamedTuple

from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.gzip import gzip_page
from django.views.generic import TemplateView
from schematools.contrib.django.models import Dataset
from schematools.types import DatasetTableSchema, DatasetFieldSchema, DatasetSchema
from schematools.naming import to_snake_case


@method_decorator(gzip_page, name="dispatch")
class DocsOverview(TemplateView):
    template_name = "dso_api/dynamic_api/docs/overview.html"

    def get_context_data(self, **kwargs):
        datasets = (ds for ds in Dataset.objects.api_enabled().db_enabled().all())
        context = super().get_context_data(**kwargs)
        context["datasets"] = [
            {
                "uri": reverse(f"dynamic_api:doc-{ds.schema.id}"),
                "title": ds.schema.title,
                "tables": [table.id for table in ds.schema.tables],
            }
            for ds in datasets
        ]
        return context


@method_decorator(gzip_page, name="dispatch")
class DatasetDocView(TemplateView):
    template_name = "dso_api/dynamic_api/docs/dataset.html"

    def get_context_data(self, **kwargs):
        d: Dataset = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=kwargs["dataset_name"]
        )
        ds: DatasetSchema = d.schema
        path = d.path

        main_title = ds.title or ds.db_name.replace("_", " ").capitalize()

        tables = [_table_context(t, path) for t in ds.tables]

        context = super().get_context_data(**kwargs)
        context.update(
            dict(
                schema=ds,
                schema_name=ds.db_name,
                schema_auth=ds.auth,
                dataset_has_auth=bool(_fix_auth(ds.auth)),
                main_title=main_title,
                tables=tables,
                swagger_url=reverse(f"dynamic_api:openapi-{ds.id}"),
            )
        )

        return context


class LookupContext(NamedTuple):
    operator: str
    value_example: Optional[str]
    description: str


# This should match ALLOWED_SCALAR_LOOKUPS in filters.parser (except for the "exact" lookup).
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


def _table_context(table: DatasetTableSchema, path: str):
    """Collect all table data for the REST API spec."""
    uri = reverse(f"dynamic_api:{table.dataset.id}-{table.id}-list")
    table_fields = table.fields
    fields = _list_fields(table_fields)
    filters = _get_filters(table_fields)

    return {
        "id": table.id,
        "title": to_snake_case(table.id).replace("_", " ").capitalize(),
        "uri": uri,
        "rest_csv": f"{uri}?_format=csv",
        "rest_geojson": f"{uri}?_format=geojson",
        "description": table.get("description"),
        "fields": [_get_field_context(field) for field in fields],
        "filters": filters,
        "auth": _fix_auth(table.auth | table.dataset.auth),
        "expands": _make_table_expands(table),
        "source": table,
        "has_geometry": table.has_geometry_fields,
    }


def _make_link(to_table: DatasetTableSchema) -> str:
    path = get_object_or_404(
        Dataset.objects.api_enabled().db_enabled(),
        name=to_table.dataset.id,
    ).path
    return reverse(f"dynamic_api:doc-{to_table.dataset.id}") + f"#{to_table.id}"


def _make_table_expands(table: DatasetTableSchema, id_separator=":"):
    """Return which relations can be expanded"""
    expands = [
        {
            "id": field.id,
            "camel_name": field.name,
            "snake_name": field.python_name,
            "relation_id": field["relation"].replace(":", id_separator),
            "target_doc_id": _make_link(field.related_table),
            "related_table": field.related_table,
        }
        for field in table.fields
        if field.get("relation") is not None
    ]

    # Reverse relations can also be expanded
    for additional_relation in table.additional_relations:
        expands.append(
            {
                "id": additional_relation.id,
                "api_name": additional_relation.name,
                "python_name": additional_relation.python_name,
                "relation_id": additional_relation.relation.replace(":", id_separator),
                "target_doc_id": _make_link(additional_relation.related_table),
                "related_table": additional_relation.related_table,
            }
        )

    return sorted(expands, key=lambda item: item["id"])


def _list_fields(table_fields) -> List[DatasetFieldSchema]:
    """List fields and their subfields in a single flat list."""
    result_fields = []
    for field in table_fields:
        if field.name == "schema":
            continue

        result_fields.append(field)
        result_fields.extend(_list_fields(field.subfields))

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
    python_name = _get_dotted_python_name(field)
    api_name = _get_dotted_api_name(field)

    type, value_example, _ = _field_data(field)
    description = field.description
    is_foreign_id = (
        field.is_subfield and field.parent_field.relation and not field.is_temporal_range
    )
    if not description and is_foreign_id and field.id in field.parent_field.related_field_ids:
        # First identifier gets parent field description.
        description = field.parent_field.description

    return {
        "id": field.id,
        "python_name": python_name,
        "api_name": api_name,
        "is_identifier": field.is_identifier_part,
        "is_deprecated": False,
        "is_relation": bool(field.relation),
        "is_foreign_id": is_foreign_id,
        "type": (type or "").capitalize(),
        "description": description or "",
        "source": field,
        "auth": _fix_auth(field.auth | field.table.auth | field.table.dataset.auth),
    }


def _get_dotted_python_name(field: DatasetFieldSchema) -> str:
    """Find the snake and camel names of a field"""
    snake_name = to_snake_case(field.id)

    parent_field = field.parent_field
    while parent_field is not None:
        parent_snake_name = to_snake_case(parent_field.id)
        snake_name = f"{parent_snake_name}.{snake_name}"
        parent_field = parent_field.parent_field

    return snake_name


def _get_dotted_api_name(field: DatasetFieldSchema) -> str:
    """Find the snake and camel names of a field"""
    camel_name = field.name
    parent_field = field.parent_field
    while parent_field is not None:
        parent_camel_name = parent_field.name
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
        if field.id == "id":
            if id_seen:
                continue
            id_seen = True
        filters.extend(_filter_context(field))
    return filters


def _filter_payload(
    field: DatasetFieldSchema, *, prefix: str = "", name_suffix: str = "", is_deprecated=False
):
    name = prefix + _get_dotted_api_name(field) + name_suffix
    type, value_example, lookups = _field_data(field)

    return {
        "name": name,
        "type": type.capitalize(),
        "is_deprecated": is_deprecated,
        "value_example": value_example or "",
        "lookups": [LOOKUP_CONTEXT[op] for op in lookups],
        "auth": _fix_auth(field.auth | field.table.auth | field.table.dataset.auth),
    }


def _filter_context(field: DatasetFieldSchema) -> List[dict[str, Any]]:
    """Return zero or more filter context(s) from the a field schema.

    This function essentially reconstructs the output of the FilterSet
    generation in the dynamic api directly from the underlying schema.
    """
    if field.relation:
        if field.is_scalar:
            # normal FKs, can now be parsed using dot-notation
            prefix = _get_dotted_api_name(field) + "."
            return [_filter_payload(id_field, prefix=prefix) for id_field in field.related_fields]
        elif field.is_composite_key:
            # composite key / temporal relation. Add those fields
            return [
                _filter_payload(sub_field)
                for sub_field in field.subfields
                if not sub_field.is_temporal_range
            ]

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
