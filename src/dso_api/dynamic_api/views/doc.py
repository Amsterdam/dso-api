"""Dataset documentation views."""
import operator
from typing import Any, FrozenSet, List, NamedTuple, Optional

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.gzip import gzip_page
from django.views.generic import TemplateView
from markdown import Markdown
from markdown.extensions.tables import TableExtension
from schematools.contrib.django.models import Dataset
from schematools.naming import to_snake_case
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema


markdown = Markdown(extensions=[TableExtension()])


@method_decorator(gzip_page, name="get")
class GenericDocs(View):
    def get(self, request, category, topic="index", *args, **kwargs):
        uri = request.build_absolute_uri(reverse("dynamic_api:api-root"))
        md = render_to_string(f"dso_api/dynamic_api/docs/{category}/{topic}.md", context={"uri": uri})
        return HttpResponse(markdown.convert(md))


@method_decorator(gzip_page, name="dispatch")
class DocsOverview(TemplateView):
    template_name = "dso_api/dynamic_api/docs/overview.html"

    def get_context_data(self, **kwargs):
        datasets = Dataset.objects.api_enabled().db_enabled()
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
        ds: DatasetSchema = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=kwargs["dataset_name"]
        ).schema

        main_title = ds.title or ds.db_name.replace("_", " ").capitalize()

        tables = [_table_context(t) for t in ds.tables]

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


class DatasetWFSDocView(TemplateView):
    """WFS-specific documentation for a single dataset."""

    template_name = "dso_api/dynamic_api/docs/dataset_wfs.html"

    def get_context_data(self, **kwargs):
        ds: DatasetSchema = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=kwargs["dataset_name"]
        ).schema

        main_title = ds.title or ds.db_name.replace("_", " ").capitalize()

        tables = [_table_context_wfs(t) for t in ds.tables]

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


def lookup_context(op, example, descr):
    # disable mark_safe() warnigns because this is static HTML in this file.
    return LookupContext(op, mark_safe(example), mark_safe(descr))  # nosec B308 B703


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
    "boolean": ("<code>true</code> | <code>false</code>", []),
    "integer": ("Geheel getal", _comparison_lookups),
    "number": ("Getal", _comparison_lookups),
    "time": ("<code>hh:mm[:ss[.ms]]</code>", _comparison_lookups),
    "date": ("<code>yyyy-mm-dd</code>", _comparison_lookups),
    "date-time": (
        "<code>yyyy-mm-dd</code> of <code>yyyy-mm-ddThh:mm[:ss[.ms]]</code>",
        _comparison_lookups,
    ),
    "uri": ("<code>https://...</code>", _string_lookups),
    "array": ("value,value", ["contains"]),  # comma separated list of strings
    "https://geojson.org/schema/Geometry.json": ("geometry", _polygon_lookups),
    "https://geojson.org/schema/Polygon.json": (
        "GeoJSON of <code>POLYGON(x y ...)</code>",
        _polygon_lookups,
    ),
    "https://geojson.org/schema/MultiPolygon.json": (
        "GeoJSON of <code>MULTIPOLYGON(x y ...)</code>",
        _polygon_lookups,
    ),
}

LOOKUP_CONTEXT = {
    lookup.operator: lookup
    for lookup in [
        lookup_context("gt", None, "Test op groter dan (<code>&gt;</code>)."),
        lookup_context("gte", None, "Test op groter dan of gelijk (<code>&gt;=</code>)."),
        lookup_context("lt", None, "Test op kleiner dan (<code>&lt;</code>)."),
        lookup_context("lte", None, "Test op kleiner dan of gelijk (<code>&lt;=</code>)."),
        lookup_context(
            "like",
            "Tekst met jokertekens (<code>*</code> en <code>?</code>).",
            "Test op gedeelte van tekst.",
        ),
        lookup_context(
            "in",
            "Lijst van waarden",
            "Test of de waarde overeenkomst met 1 van de opties (<code>IN</code>).",
        ),
        lookup_context("not", None, "Test of waarde niet overeenkomt (<code>!=</code>)."),
        lookup_context(
            "contains", "Comma gescheiden lijst", "Test of er een intersectie is met de waarde."
        ),
        lookup_context(
            "isnull",
            "<code>true</code> of <code>false</code>",
            "Test op ontbrekende waarden (<code>IS NULL</code> / <code>IS NOT NULL</code>).",
        ),
        lookup_context(
            "isempty",
            "<code>true</code> of <code>false</code>",
            "Test of de waarde leeg is (<code>== ''</code> / <code>!= ''</code>)",
        ),
    ]
}


def _table_context(table: DatasetTableSchema):
    """Collect all table data for the REST API spec."""
    uri = reverse(f"dynamic_api:{table.dataset.id}-{table.id}-list")
    table_fields = table.fields
    fields = _list_fields(table_fields)
    filters = _get_filters(table_fields)

    return {
        "id": table.id,
        "title": to_snake_case(table.id).replace("_", " ").capitalize(),
        "uri": uri,
        "description": table.get("description"),
        "fields": [_get_field_context(field) for field in fields],
        "filters": filters,
        "auth": _fix_auth(table.auth | table.dataset.auth),
        "expands": _make_table_expands(table),
        "source": table,
        "has_geometry": table.has_geometry_fields,
    }


def _table_context_wfs(table: DatasetTableSchema):
    """Collect table data for the WFS server spec."""
    uri = reverse("dynamic_api:wfs", kwargs={"dataset_name": table.dataset.id})
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table.id)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "typenames": [f"app:{snake_id}", snake_id],
        "uri": uri,
        "description": table.get("description"),
        "fields": [_get_field_context(field) for field in (_list_fields(table.fields))],
        "auth": _fix_auth(table.dataset.auth | table.auth),
        "expands": _make_table_expands(table),
        "source": table,
        "has_geometry": table.has_geometry_fields,
        "wfs_typename": f"app:{snake_name}",
        "wfs_csv": (
            f"{uri}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            f"&TYPENAMES={snake_id}&OUTPUTFORMAT=csv"
            if table.has_geometry_fields
            else ""
        ),
        "wfs_geojson": (
            f"{uri}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
            f"&TYPENAMES={snake_id}&OUTPUTFORMAT=geojson"
            if table.has_geometry_fields
            else ""
        ),
    }


def _make_link(to_table: DatasetTableSchema) -> str:
    return reverse(f"dynamic_api:doc-{to_table.dataset.id}") + f"#{to_table.id}"


def _make_table_expands(table: DatasetTableSchema):
    """Return which relations can be expanded"""
    expands = [
        {
            "id": field.id,
            "api_name": field.name,
            "python_name": field.python_name,
            "relation_id": field["relation"],
            "target_doc": _make_link(field.related_table),
            "related_table": field.related_table,
        }
        for field in table.fields
        if field.get("relation") is not None
    ]

    # Reverse relations can also be expanded
    expands.extend(
        (
            {
                "id": additional_relation.id,
                "api_name": additional_relation.name,
                "python_name": additional_relation.python_name,
                "relation_id": additional_relation.relation,
                "target_doc": _make_link(additional_relation.related_table),
                "related_table": additional_relation.related_table,
            }
            for additional_relation in table.additional_relations
        )
    )

    return sorted(expands, key=operator.itemgetter("id"))


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
        type = type[len("https://geojson.org/schema/") : -5]
        value_example = f"GeoJSON of <code>{type.upper()}(x y ...)<code>"
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

    type, _, _ = _field_data(field)
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
        "value_example": mark_safe(value_example or ""),  # nosec B308 B703 (is static HTML)
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
