"""Dataset documentation views."""
import logging
import operator
from typing import Any, FrozenSet, Iterable, List, NamedTuple, Optional

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from markdown import Markdown
from markdown.extensions.tables import TableExtension
from schematools.contrib.django.models import Dataset
from schematools.naming import to_snake_case
from schematools.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema

from dso_api.dynamic_api.filters.parser import QueryFilterEngine

logger = logging.getLogger(__name__)

markdown = Markdown(extensions=[TableExtension(), "fenced_code"])

CACHE_DURATION = 3600  # seconds.

decorators = [cache_page(CACHE_DURATION)]


def search(request: HttpRequest) -> HttpResponse:
    template = "dso_api/dynamic_api/docs/search.html"
    query = request.GET.get("q", "").strip()
    return HttpResponse(render_to_string(template, context={"query": query}))


@cache_page(CACHE_DURATION)
def search_index(_request) -> HttpResponse:
    index = {}
    for ds in Dataset.objects.api_enabled().db_enabled():
        try:
            uri = reverse(f"dynamic_api:doc-{ds.schema.id}")
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


@method_decorator(decorators, name="get")
class GenericDocs(View):
    PRE = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Amsterdam DataPunt API Documentatie</title>
      <link rel="stylesheet" type="text/css"
            href="/v1/static/rest_framework/css/bootstrap.min.css"/>
      <link rel="stylesheet" type="text/css"
            href="/v1/static/rest_framework/css/bootstrap-tweaks.css"/>
      <link rel="stylesheet" type="text/css"
            href="/v1/static/rest_framework/css/default.css"/>
    </head>
    <body>
      <div class="container">

    <h2>Introductie API Keys</h2>
    <blockquote style="border-color: #ec0101">
        <p>
            Het Dataplatform van de gemeente Amsterdam gaat het gebruik van een identificatie key
            bij het aanroepen van haar API's vanaf 1 februari 2024 verplicht stellen.
            Vanaf 1 februari 2024 kun je de API's van het Dataplatform niet meer zonder
            een key gebruiken. Vraag tijdig een key aan via dit aanvraagformulier.
            Doe je dit niet, dan werkt je applicatie of website vanaf 1 februari 2024 niet meer.
            Dit geldt voor alle API's die op deze pagina gedocumenteerd zijn.
        </p>
        <p>
            Door de API key kunnen we contact houden met de gebruikers van onze API's.
            Zo kunnen we gebruikers informeren over updates.
            Daarnaast krijgen we hiermee inzicht in het gebruik van de API's
            en in wie welke dataset via de API bevraagt.
            Ook voor dataeigenaren is dit waardevolle informatie.
        </p>
        <p>
            Meer info: <br>
            <a href="{settings.KEYS_API_URL}clients/v1/register/">
                Pagina API key aanvragen</a> <br>
            <a href="{settings.KEYS_API_URL}clients/v1/docs/">
                Technische documentatie</a> <br>
            Vragen? Mail naar dataplatform@amsterdam.nl <br>
        <p>
    </blockquote>

    """

    POST = """</div></body></html>"""

    def get(self, request, category, topic="index", *args, **kwargs):
        uri = request.build_absolute_uri(reverse("dynamic_api:api-root"))
        template = f"dso_api/dynamic_api/docs/{category}/{topic}.md"
        try:
            md = render_to_string(template, context={"uri": uri})
        except TemplateDoesNotExist as e:
            raise Http404() from e
        html = markdown.convert(md)
        return HttpResponse(self.PRE + html + self.POST)


@method_decorator(decorators, name="dispatch")
class DocsOverview(TemplateView):
    template_name = "dso_api/dynamic_api/docs/overview.html"

    def get_context_data(self, **kwargs):
        datasets = []
        for ds in Dataset.objects.api_enabled().db_enabled():
            try:
                uri = reverse(f"dynamic_api:doc-{ds.schema.id}")
            except NoReverseMatch as e:
                logger.warning("dataset %s: %s", ds.schema.id, e)
                continue
            datasets.append(
                {
                    "id": ds.schema.id,
                    "uri": uri,
                    "title": ds.schema.title or ds.schema.id,
                    "tables": [table.id for table in ds.schema.tables],
                }
            )
        datasets.sort(key=lambda ds: ds["title"].lower())

        context = super().get_context_data(**kwargs)
        context["datasets"] = datasets
        return context


@method_decorator(decorators, name="dispatch")
class DatasetDocView(TemplateView):
    template_name = "dso_api/dynamic_api/docs/dataset.html"

    def get_context_data(self, **kwargs):
        dataset_name = to_snake_case(kwargs["dataset_name"])
        ds: Dataset = get_object_or_404(
            Dataset.objects.api_enabled().db_enabled(), name=dataset_name
        )
        ds_schema: DatasetSchema = ds.schema

        main_title = ds_schema.title or ds_schema.db_name.replace("_", " ").capitalize()

        try:
            if "name" in ds_schema.publisher:
                publisher = ds_schema.publisher["name"]
            elif isinstance(ds_schema.publisher, dict) and "$ref" in ds_schema.publisher:
                publisher = ds_schema.publisher["$ref"]
                publisher = publisher.lstrip("/").removeprefix("publishers/")
        except NotImplementedError:  # Work around schema loaders being broken in tests.
            publisher = "N/A"

        tables = [_table_context(ds, t) for t in ds_schema.tables]

        context = super().get_context_data(**kwargs)
        context.update(
            dict(
                schema=ds,
                schema_name=ds_schema.db_name,
                schema_auth=ds_schema.auth,
                dataset_has_auth=bool(_fix_auth(ds_schema.auth)),
                main_title=main_title,
                publisher=publisher,
                tables=tables,
                swagger_url=reverse(f"dynamic_api:openapi-{ds_schema.id}"),
            )
        )

        return context


@method_decorator(decorators, name="dispatch")
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
    # disable mark_safe() warnings because this is static HTML in this very file.
    return LookupContext(op, mark_safe(example), mark_safe(descr))  # nosec B308 B703


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


def _table_context(ds: Dataset, table: DatasetTableSchema):
    """Collect all table data for the REST API spec."""
    dataset_name = to_snake_case(table.dataset.id)
    table_name = to_snake_case(table.id)
    uri = reverse(f"dynamic_api:{dataset_name}-{table_name}-list")
    fields = _list_fields(table.fields)
    filters = _get_filters(table.fields)
    exports = []
    # if dataset_name in settings.EXPORTED_DATASETS.split(","):
    if ds.enable_export:
        export_info = []
        for type_, extension in (
            ("csv", "csv"),
            ("geopackage", "gpkg"),
            ("jsonlines", "jsonl"),
        ):
            ext_info = {
                "extension": extension,
                "type": type_,
                "url": f"{settings.EXPORT_BASE_URI}/{type_}/"
                f"{dataset_name}_{table_name}.{extension}.zip",
            }
            export_info.append(ext_info)
        exports.append(export_info)

    if (temporal := table.temporal) is not None:
        for name, fields in temporal.dimensions.items():
            filters.append(
                {
                    "name": name,
                    "type": "Datetime",
                    "value_example": "<code>yyyy-mm-dd</code> of "
                    "<code>yyyy-mm-ddThh:mm[:ss[.ms]]</code>",
                }
            )

    filters.sort(key=operator.itemgetter("name"))

    return {
        "id": table.id,
        "title": to_snake_case(table.id).replace("_", " ").capitalize(),
        "uri": uri,
        "exports": exports,
        "description": table.get("description"),
        "fields": [ctx for field in fields for ctx in _get_field_context(field, wfs=False)],
        "filters": filters,
        "auth": _fix_auth(table.auth | table.dataset.auth),
        "expands": _make_table_expands(table, wfs=False),
        "source": table,
        "has_geometry": table.has_geometry_fields,
    }


def _table_context_wfs(table: DatasetTableSchema):
    """Collect table data for the WFS server spec."""
    uri = reverse("dynamic_api:wfs", kwargs={"dataset_name": table.dataset.id})
    snake_name = to_snake_case(table.dataset.id)
    snake_id = to_snake_case(table.id)
    fields = _list_fields(table.fields)

    return {
        "title": snake_id.replace("_", " ").capitalize(),
        "typenames": [f"app:{snake_id}", snake_id],
        "uri": uri,
        "description": table.get("description"),
        "fields": [ctx for field in fields for ctx in _get_field_context(field, wfs=True)],
        "auth": _fix_auth(table.dataset.auth | table.auth),
        "expands": _make_table_expands(table, wfs=True),
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


def _make_table_expands(table: DatasetTableSchema, wfs: bool):
    """Return which relations can be expanded"""
    expands = [
        {
            "id": field.id,
            "name": field.python_name if wfs else field.name,
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
                "name": additional_relation.python_name if wfs else additional_relation.name,
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
        lookups = []
    elif field.relation or "://" in type:
        lookups = _identifier_lookups
        if field.type == "string":
            lookups += [lookup for lookup in _string_lookups if lookup not in lookups]

    return type, value_example, lookups


def _get_field_context(field: DatasetFieldSchema, wfs: bool) -> Iterable[dict[str, Any]]:
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
        "name": _get_dotted_python_name(field) if wfs else _get_dotted_api_name(field),
        "is_identifier": field.is_identifier_part,
        "is_deprecated": False,
        "is_relation": is_foreign_id or bool(field.relation),
        "type": (type or "").capitalize(),
        "description": description or "",
        "source": field,
        "auth": auth,
    }

    if not field.relation or not wfs:
        return

    # Yield another context for relations with the old "Id" suffix.
    yield {
        "id": field.id,
        "name": field.id + "Id",
        "is_identifier": field.is_identifier_part,
        "is_deprecated": True,
        "is_relation": True,
        "type": (type or "").capitalize(),
        "description": description or "",
        "source": field,
        "auth": auth,
    }


def _get_dotted_python_name(field: DatasetFieldSchema) -> str:
    snake_name = to_snake_case(field.id)

    parent_field = field.parent_field
    while parent_field is not None:
        parent_snake_name = to_snake_case(parent_field.id)
        snake_name = f"{parent_snake_name}.{snake_name}"
        parent_field = parent_field.parent_field

    return snake_name


def _get_dotted_api_name(field: DatasetFieldSchema) -> str:
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


def _fix_auth(auth: FrozenSet[str]) -> FrozenSet[str]:
    """Hide the OPENBAAR tag.
    When the dataset is public, but table isn't,
    this could even mix authorization levels.
    """
    return auth - {"OPENBAAR"}
