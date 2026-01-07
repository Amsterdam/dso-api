"""These views service documentation of the available datasets.

By implementing this part of the documentation as Django views,
the dataset definitions are always in sync with the actual live data models.
"""

import logging
import operator
import re
from collections.abc import Iterable
from typing import Any, NamedTuple
from urllib.parse import urljoin

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from markdown import Markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.tables import TableExtension
from schematools.contrib.django.models import Dataset
from schematools.naming import to_snake_case
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema

from dso_api.dynamic_api.constants import DEFAULT
from dso_api.dynamic_api.filters.parser import QueryFilterEngine

logger = logging.getLogger(__name__)

markdown = Markdown(
    extensions=[
        TableExtension(),
        "fenced_code",
        CodeHiliteExtension(use_pygments=True, noclasses=False),
    ]
)

cache_doc_page = cache_page(timeout=36000)  # seconds


def search(request: HttpRequest) -> HttpResponse:
    template = "dso_api/dynamic_api/docs/search.html"
    query = request.GET.get("q", "").strip()
    return HttpResponse(render_to_string(template, context={"query": query}))


@cache_doc_page
def search_index(_request) -> HttpResponse:
    index = {}
    for ds in Dataset.objects.api_enabled().db_enabled():
        try:
            uri = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": ds.schema.id})
        except NoReverseMatch as e:
            logger.warning("dataset %s: %s", ds.schema.id, e)
            continue
        schema: DatasetSchema = ds.schema
        index[uri] = {
            "description": schema.description,
            "fields": [
                (f.title or "") + " " + f.id + " " + (f.description or "")
                for t in schema.get_tables()
                for f in t.fields
            ],
            "id": schema.id,
            "title": schema.title,
        }

    return JsonResponse(index)


@method_decorator(cache_doc_page, name="get")
class GenericDocs(TemplateView):
    """Documentation pages from ``/v1/docs/generic/...``."""

    template_name = "dso_api/dynamic_api/docs/base_markdown.html"
    CATEGORY_TITLE = {
        "gis": "Geo API's",
        "rest": "REST API's",
    }

    def get_context_data(self, **kwargs):
        category = self.kwargs["category"]
        topic = self.kwargs["topic"]
        uri = self.request.build_absolute_uri(reverse("dynamic_api:api-root"))
        template = f"dso_api/dynamic_api/docs/{category}/{topic}.md"
        try:
            md = render_to_string(template, context={"uri": uri})
        except TemplateDoesNotExist as e:
            raise Http404() from e

        html = markdown.convert(md)
        html = html.replace("<table>", '<table class="table">').replace('.md"', '.html"')

        # Take first <h1> as document title
        if match := re.search("<h1>([^<]+)</h1>", html):
            markdown_title = match.group(1)
        else:
            markdown_title = topic

        return {
            "category": category,
            "topic": topic,
            "category_title": self.CATEGORY_TITLE.get(category, category.title()),
            "markdown_title": markdown_title,
            "markdown_content": mark_safe(html),  # noqa: S308
            "apikey_register_url": urljoin(settings.APIKEYSERV_API_URL, "/clients/v1/register/"),
        }


@method_decorator(cache_doc_page, name="dispatch")
class DocsIndexView(TemplateView):
    """The ``/v1/docs/index.html`` page."""

    template_name = "dso_api/dynamic_api/docs/index.html"

    def get_context_data(self, **kwargs):
        datasets = []
        for ds in Dataset.objects.api_enabled().db_enabled():
            try:
                docs_url = reverse(
                    "dynamic_api:docs-dataset", kwargs={"dataset_name": ds.schema.id}
                )
            except NoReverseMatch as e:
                logger.warning("dataset %s: %s", ds.schema.id, e)
                continue

            datasets.append(
                {
                    "id": ds.schema.id,
                    "path": ds.path,
                    "description": ds.schema.description or "",
                    "docs_url": docs_url,
                    "has_geometry_fields": ds.has_geometry_fields,
                    "title": ds.schema.title or ds.schema.id,
                    "tables": ds.schema.tables,
                }
            )
        datasets.sort(key=lambda ds: ds["title"].lower())

        context = super().get_context_data(**kwargs)
        context["datasets"] = datasets
        return context


@method_decorator(cache_doc_page, name="dispatch")
class DatasetDocView(TemplateView):
    """REST API-specific documentation for a single dataset (``/v1/docs/datasets/...```)."""

    template_name = "dso_api/dynamic_api/docs/dataset.html"

    def get_context_data(self, **kwargs):
        dataset_name = to_snake_case(kwargs["dataset_name"])
        ds: Dataset = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=dataset_name
        )
        dataset_version = kwargs["dataset_version"]
        ds_schema: DatasetSchema = ds.schema
        main_title = ds_schema.title or ds_schema.db_name.replace("_", " ").capitalize()
        tables = [
            _table_context(ds, t, dataset_version)
            for t in ds_schema.get_version(
                ds.default_version if dataset_version == DEFAULT else dataset_version
            ).tables
        ]
        pattern_suffix = "" if dataset_version == DEFAULT else "-version"
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "dataset": ds,
                "schema": ds_schema,
                "schema_name": ds_schema.db_name,
                "schema_auth": ds_schema.auth,
                "dataset_version": dataset_version,
                "dataset_has_auth": bool(_fix_auth(ds_schema.auth)),
                "main_title": main_title,
                "tables": tables,
                "oauth_url": settings.OAUTH_URL,
                "swagger_url": reverse(
                    f"dynamic_api:openapi{pattern_suffix}",
                    kwargs={"dataset_name": ds_schema.id, "dataset_version": dataset_version},
                ),
                "wfs_url": (
                    reverse(
                        f"dynamic_api:wfs{pattern_suffix}",
                        kwargs={"dataset_name": ds_schema.id, "dataset_version": dataset_version},
                    )
                    if ds.has_geometry_fields
                    else None
                ),
                "mvt_url": (
                    reverse(
                        f"dynamic_api:mvt{pattern_suffix}",
                        kwargs={"dataset_name": ds_schema.id, "dataset_version": dataset_version},
                    )
                    if ds.has_geometry_fields
                    else None
                ),
            }
        )

        return context


class LookupContext(NamedTuple):
    operator: str
    value_example: str | None
    description: str


def lookup_context(op, example, descr):
    # disable mark_safe() warnings because this is static HTML in this very file.
    return LookupContext(op, mark_safe(example or ""), mark_safe(descr or ""))  # noqa: S308


# This should match ALLOWED_SCALAR_LOOKUPS in filters.parser (except for the "exact" lookup).
_identifier_lookups = ["in", "not", "isnull"]
_string_lookups = ["in", "like", "not", "isnull", "isempty"]

FORMAT_ALIASES = {
    "date-time": "Datetime",
}

VALUE_EXAMPLES = {
    "string": "Tekst",
    "boolean": "<code>true</code> | <code>false</code>",
    "integer": "Geheel getal",
    "number": "Getal",
    "time": "<code>hh:mm[:ss[.ms]]</code>",
    "date": "<code>yyyy-mm-dd</code>",
    "date-time": "<code>yyyy-mm-dd</code> of <code>yyyy-mm-ddThh:mm[:ss[.ms]]</code>",
    "uri": "<code>https://...</code>",
    "array": "value1,value2",  # comma separated list of strings
    "https://geojson.org/schema/Geometry.json": "geometry",
    "https://geojson.org/schema/Polygon.json": "GeoJSON of <code>POLYGON(x y ...)</code>",
    "https://geojson.org/schema/MultiPolygon.json": (
        "GeoJSON of <code>MULTIPOLYGON(x y ...)</code>"
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
            "contains", "Kommagescheiden lijst", "Test of er een intersectie is met de waarde."
        ),
        lookup_context(
            "intersects",
            "GeoJSON of <code>POLYGON(x y ...)</code>",
            "Test of er een intersectie is met de waarde.",
        ),
        lookup_context(
            "isnull",
            "<code>true</code> | <code>false</code>",
            "Test op ontbrekende waarden (<code>IS NULL</code> / <code>IS NOT NULL</code>).",
        ),
        lookup_context(
            "isempty",
            "<code>true</code> | <code>false</code>",
            "Test of de waarde leeg is (<code>== ''</code> / <code>!= ''</code>)",
        ),
    ]
}


def _table_context(ds: Dataset, table: DatasetTableSchema, dataset_version: str):
    """Collect all table data for the REST API spec."""
    dataset_name = to_snake_case(table.dataset.id)
    table_name = to_snake_case(table.id)
    vmajor = ds.default_version if dataset_version == DEFAULT else dataset_version
    pattern_version = "" if dataset_version == DEFAULT else f"-{dataset_version}"
    uri = reverse(f"dynamic_api:{dataset_name}{pattern_version}-{table_name}-list")
    fields = _list_fields(table.fields)
    filters = _get_filters(table.fields)
    exports = []
    version = ds.versions.get(version=vmajor)
    # if dataset_name in settings.EXPORTED_DATASETS.split(","):
    table_instance = version.tables.get(name=table_name)
    if table_instance.enable_export:
        export_info = []
        for type_, extension, description in (
            ("csv", "csv", "CSV"),
            ("geopackage", "gpkg", "geopackage"),
            ("jsonlines", "jsonl", "JSONlines"),
            ("geojson", "geojson", "GeoJSON"),
        ):
            # Als FP/MDW op dataset/tabel/veld auth zit, is er een vertrouwelijke bulk link
            if (
                ds.auth == "FP/MDW"
                or table_instance.auth == "FP/MDW"
                or table_instance.fields.filter(auth="FP/MDW").exists()
            ):
                url = (
                    f"{settings.CONFIDENTIAL_EXPORT_BASE_URI}/{type_}/"
                    f"{dataset_name}_{table_name}.{extension}.zip"
                )
                if not url.startswith("http"):  # The settings urls are not prefixed with https://
                    url = f"https://{url}"
                ext_info = {
                    "extension": extension,
                    "type": type_,
                    "description": description,
                    "url": url,
                    "kind": "confidential",
                }
                export_info.append(ext_info)

            # Voor openbare data (ook slechts indien een subset van de velden) is er een reguliere
            # bulk link
            if (
                ds.auth == "OPENBAAR"
                and table_instance.auth == "OPENBAAR"
                and table_instance.fields.filter(auth="OPENBAAR").exists()
            ):
                url = (
                    f"{settings.EXPORT_BASE_URI}/{type_}/"
                    f"{dataset_name}_{table_name}.{extension}.zip"
                )
                if not url.startswith("http"):  # The settings urls are not prefixed with https://
                    url = f"https://{url}"
                ext_info = {
                    "extension": extension,
                    "type": type_,
                    "description": description,
                    "url": url,
                    "kind": "public",
                }
                export_info.append(ext_info)
        exports.append(export_info)

    if (temporal := table.temporal) is not None:
        for name in temporal.dimensions:
            filters.append(
                {
                    "name": name,
                    "type": "Datetime",
                    "value_example": mark_safe(VALUE_EXAMPLES["date-time"]),  # noqa: S308
                }
            )

    filters.sort(key=operator.itemgetter("name"))

    return {
        "id": table.id,
        "name": to_snake_case(table.id).replace("_", " ").capitalize(),
        "table_schema": table,
        "uri": uri,
        "exports": exports,
        "description": table.get("description"),
        "fields": [ctx for field in fields for ctx in _get_field_context(field)],
        "filters": filters,
        "auth": _fix_auth(table.auth | table.dataset.auth),
        "expands": _make_table_expands(table),
        "source": table,
        "has_geometry": table.has_geometry_fields,
        "subresources": _make_table_subresources(table, uri),
    }


def _make_link(to_table: DatasetTableSchema) -> str:
    url = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": to_table.dataset.id})
    return f"{url}#{to_table.id}"


def _make_table_expands(table: DatasetTableSchema):
    """Return which relations can be expanded"""
    expands = [
        {
            "id": field.id,
            "name": field.name,
            "relation_id": field["relation"],
            "target_doc": _make_link(field.related_table),
            "related_table": field.related_table,
        }
        for field in table.fields
        if field.get("relation") is not None
    ]

    # Reverse relations can also be expanded
    expands.extend(
        {
            "id": additional_relation.id,
            "name": additional_relation.name,
            "relation_id": additional_relation.relation,
            "target_doc": _make_link(additional_relation.related_table),
            "related_table": additional_relation.related_table,
        }
        for additional_relation in table.additional_relations
    )

    return sorted(expands, key=operator.itemgetter("id"))


def _make_table_subresources(table: DatasetTableSchema, base_url: str) -> dict[str, str]:
    result = {}
    for subresource in table.subresources:
        url = f"{base_url}/{{{to_snake_case(table.id)}_id}}/{to_snake_case(subresource.table.id)}"
        result[subresource.table.id] = url
        # merge subresource's subresources
        result = result | _make_table_subresources(subresource.table, url)
    return result


def _list_fields(table_fields) -> list[DatasetFieldSchema]:
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
        value_example = VALUE_EXAMPLES[format or type]
        lookups = QueryFilterEngine.get_allowed_lookups(field) - {""}
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
        # Keep the lookups from get_allowed_lookups for geometry fields
        if not lookups:
            lookups = QueryFilterEngine.get_allowed_lookups(field) - {""}
    elif field.relation or "://" in type:
        lookups = _identifier_lookups
        if field.type == "string":
            lookups += [lookup for lookup in _string_lookups if lookup not in lookups]

    return type, value_example, lookups


def _get_field_context(field: DatasetFieldSchema) -> Iterable[dict[str, Any]]:
    """Get context data for a field."""
    type, _, _ = _field_data(field)
    description = field.description
    is_foreign_id = (
        field.is_subfield and field.parent_field.relation and not field.is_temporal_range
    )
    if not description and is_foreign_id and field.id in field.parent_field.related_field_ids:
        # First identifier gets parent field description.
        description = field.parent_field.description
    auth = _fix_auth(field.auth | field.table.auth | field.table.dataset.auth)

    yield {
        "id": field.id,
        # WFS uses the ORM names of fields.
        "name": _get_dotted_api_name(field),
        "title": field.title,
        "is_identifier": field.is_identifier_part,
        "is_deprecated": False,
        "is_relation": is_foreign_id or bool(field.relation),
        "type": (type or "").capitalize(),
        "description": description or "",
        "source": field,
        "auth": auth,
    }


def _get_dotted_api_name(field: DatasetFieldSchema) -> str:
    camel_name = field.name
    parent_field = field.parent_field
    while parent_field is not None:
        parent_camel_name = parent_field.name
        camel_name = f"{parent_camel_name}.{camel_name}"
        parent_field = parent_field.parent_field

    return camel_name


def _get_filters(table_fields: list[DatasetFieldSchema]) -> list[dict[str, Any]]:
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
        "value_example": mark_safe(value_example or ""),  # noqa: S308 (is static HTML)
        "lookups": [LOOKUP_CONTEXT[op] for op in lookups],
        "auth": _fix_auth(field.auth | field.table.auth | field.table.dataset.auth),
    }


def _filter_context(field: DatasetFieldSchema) -> list[dict[str, Any]]:
    """Return zero or more filter context(s) from a field schema.

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


def _fix_auth(auth: frozenset[str]) -> frozenset[str]:
    """Hide the OPENBAAR tag.
    When the dataset is public, but table isn't,
    this could even mix authorization levels.
    """
    return auth - {"OPENBAAR"}
