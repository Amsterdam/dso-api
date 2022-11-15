"""The engine for filtering from the query-string.

This translates a query-string into ORM lookups using the Amsterdam Schema definitions.
"""
from __future__ import annotations

import operator
from datetime import datetime
from functools import reduce
from typing import Any, NamedTuple

from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.models import Q
from django.utils.datastructures import MultiValueDict
from gisserver.geometries import CRS
from rest_framework.exceptions import ValidationError
from schematools.exceptions import SchemaObjectNotFound
from schematools.permissions import UserScopes
from schematools.types import AdditionalRelationSchema, DatasetFieldSchema, DatasetTableSchema

from dso_api.dynamic_api.permissions import check_filter_field_access
from dso_api.dynamic_api.temporal import TemporalTableQuery, get_request_date

from .values import str2bool, str2geo, str2isodate, str2number, str2time

# Lookups that have specific value types:

LOOKUP_PARSERS = {
    "isnull": str2bool,
    "isempty": str2bool,
    "like": str,  # e.g. uri is parsed as string for like.
}

# Array field lookups are not mentioned here, but handled with if/else cases
# because the 'contains' lookup value differs between array fields and geometry fields.
MULTI_VALUE_LOOKUPS = {"not", "in"}  # lookups that may hold multiple values in the query string
SPLIT_VALUE_LOOKUPS = {"in"}  # lookups that take comma-separated values lists
LOOKUP_MERGE_OPERATORS = {"not": operator.and_}  # which ones should be merged for the QuerySet

SCALAR_PARSERS = {
    "boolean": str2bool,
    "string": str,
    "integer": int,
    "number": str2number,
    # Format variants for type string:
    "date": str2isodate,
    "date-time": str2isodate,
    "time": str2time,
    "uri": str,
}

# The empty value is there to indicate the field also supports no lookup operator.
# This is mostly used by the OpenAPI generator.
_comparison_lookups = {"", "gte", "gt", "lt", "lte", "in", "not", "isnull"}
_polygon_lookups = {"", "contains", "isnull", "not"}
_string_lookups = {"", "in", "isnull", "not", "isempty", "like"}

ALLOWED_IDENTIFIER_LOOKUPS = {"", "in", "not", "isnull"}

# These definitions are also used to generate the OpenAPI spec.
# NOTE: for the end-user docs, update docs/source/datasets.py manually.
ALLOWED_SCALAR_LOOKUPS = {
    "boolean": {"", "isnull"},
    "integer": _comparison_lookups,
    "number": _comparison_lookups,
    "string": _string_lookups,
    "array": {"", "contains"},
    "object": set(),
    "https://geojson.org/schema/Geometry.json": _polygon_lookups,  # Assume it works.
    "https://geojson.org/schema/Point.json": {"", "isnull", "not"},
    "https://geojson.org/schema/Polygon.json": _polygon_lookups,
    "https://geojson.org/schema/MultiPolygon.json": _polygon_lookups,
    # Format variants for type string:
    "date": _comparison_lookups,
    "date-time": _comparison_lookups,
    "time": _comparison_lookups,
    "uri": _string_lookups,
}


class FilterInput:
    """The data for a single filter parameter.
    This contains the parsed details from a single parameter,
    for example: "?someField[isnull]=false"
    """

    def __init__(self, key: str, path: list[str], lookup: str | None, raw_values: list[str]):
        self.key = key
        self.path = path
        self.lookup = lookup or ""
        self._raw_values = raw_values

    @classmethod
    def from_parameter(cls, key: str, raw_values: list[str]) -> FilterInput:
        """Construct this parsed class from a single query parameter."""
        bracket = key.find("[")
        if bracket == -1:
            if "]" in key:
                # Close bracket but no open bracket. Brackets don't occur in field paths.
                raise ValidationError(f"missing open bracket ([) in {key!r}")
            path = key
            lookup = None
        elif not key.endswith("]"):
            raise ValidationError(f"last character of {key!r} must be closing bracket (])")
        elif bracket == 0:
            raise ValidationError(f"empty field path in {key!r}")
        else:
            path = key[:bracket]
            lookup = key[bracket + 1 : -1]

        path = path.split(".")
        if "" in path:
            raise ValidationError(f"empty element in field path {key!r}")

        return cls(
            key=key,
            path=path,
            lookup=lookup,
            raw_values=raw_values,
        )

    def __str__(self):
        return self.key

    @property
    def raw_value(self) -> str:
        """Returns a single value when the filter expects this."""
        return self._raw_values[0]

    @property
    def raw_values(self) -> list[str]:
        """Returns a list of all provided values.
        This is useful for filters that may occur multiple times
        in a query string, such as: field[not]=abc&field[not]=def
        """
        return self._raw_values

    @property
    def split_values(self) -> list[str]:
        """Returns the first value, split on comma.
        This is used for values such as: array=..., array[contains]=... or field[in]=...
        """
        # Value is comma separated (field[in]=...).
        return self._raw_values[0].split(",")


class QueryFilterEngine:
    """Translate query-string filters into filter queries.

    This uses the Amsterdam Schema details to determine which filters are allowed,
    and map those on the model/queryset parameters.

    This strategy also allows spanning relations, as the input doesn't have
    to match the API serializer class. Instead, the dotted-paths in the
    querystring are directly mapped against schema fields.
    """

    NON_FILTER_PARAMS = {
        # Allowed request parameters.
        # Except for "page", all the non-underscore-prefixed parameters
        # are for backward compatibility.
        "_count",
        "_expand",
        "_expandScope",
        "_fields",
        "fields",
        "_format",
        "format",
        "_pageSize",
        "page_size",
        "page",
        "_sort",
        "sorteer",
    }

    @classmethod
    def from_request(cls, request):
        """Construct the parser from the request data."""
        return cls(
            user_scopes=request.user_scopes,
            query=request.GET,
            input_crs=getattr(request, "accept_crs", None),
            request_date=get_request_date(request),
        )

    def __init__(
        self, user_scopes: UserScopes, query: MultiValueDict, input_crs: CRS, request_date=None
    ):
        self.user_scopes = user_scopes
        self.query = query
        self.input_crs = input_crs
        self.filter_inputs = self._parse_filters(query)
        self.request_date = request_date

    def __bool__(self):
        return bool(self.filter_inputs)

    def _parse_filters(self, query: MultiValueDict) -> list[FilterInput]:
        """Translate raw HTTP GET parameters into a Python structure"""
        filters = []

        for key in sorted(query):
            if key in self.NON_FILTER_PARAMS:
                continue

            filters.append(FilterInput.from_parameter(key, query.getlist(key)))

        return filters

    def filter_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply the filtering"""
        compiled_filter = self._compile_filters(queryset.model.table_schema())
        if compiled_filter is not None:
            try:
                queryset = queryset.filter(compiled_filter.q_object)
            except DjangoValidationError as e:
                raise ValidationError(list(e)) from e
            except FieldError as e:
                # XXX This can happen when a [like] query is done against a relation field, such as
                # https://api.data.amsterdam.nl/v1/meldingen/statistieken/?buurt.identificatie[like]=X.
                # According to the docs, we should support that, but Django doesn't grok it.
                # For now, an informative 400 is better than a 500.
                raise ValidationError(e) from e

            if compiled_filter.is_many:
                queryset = queryset.distinct()

        return queryset

    def _compile_filters(self, table_schema: DatasetTableSchema) -> CompiledFilter | None:
        """Create the filters based on the table schem and current request query string."""
        filters = []
        for filter_input in self.filter_inputs:
            if table_schema.temporal and filter_input.key in table_schema.temporal.dimensions:
                # Skip handling of temporal fields, is handled elsewhere.
                continue

            filters.append(self._compile_filter(table_schema, filter_input))

        if not filters:
            return None
        else:
            # Merge the results
            q = reduce(operator.and_, (filter.q_object for filter in filters))
            is_many = any(filter.is_many for filter in filters)
            return CompiledFilter(q, is_many)

    def _compile_filter(
        self, table_schema: DatasetTableSchema, filter_input: FilterInput
    ) -> CompiledFilter:
        """Build the Q() object for a single filter"""
        parts = _parse_filter_path(filter_input.path, table_schema, self.user_scopes)
        orm_path = _to_orm_path(parts)

        value = self._translate_raw_value(filter_input, parts[-1])
        lookup = self._translate_lookup(filter_input, parts[-1], value)
        q_path = f"{orm_path}__{lookup}"

        operator = LOOKUP_MERGE_OPERATORS.get(filter_input.lookup)
        if operator is not None:
            # for [not] lookup: field != 1 AND field != 2
            q_object = reduce(operator, (Q(**{q_path: v}) for v in value))
        else:
            q_object = Q(**{q_path: value})

        # Make sure loose relations don't return all historical records,
        # but only match the selected point in time.
        # Don't do this for isnull, which checks whether a relation exists at all.
        if lookup != "isnull":
            if temporal_lookups := self._create_temporal_filters(parts):
                q_object &= temporal_lookups

        # Also tell whether the filter-path walks over many-to-many relationships.
        # These will need extra care to avoid duplicate results in the final filter call.
        is_many = any(part.is_many for part in parts) or any(
            # When joining from a loose relation (not as last field),
            # avoid returning multiple objects.
            (not part.reverse_field and part.field.is_loose_relation)
            for part in parts[:-1]
        )
        return CompiledFilter(q_object, is_many)

    def _create_temporal_filters(self, parts: list[FilterPathPart]) -> Q | None:
        """For loose relations, find the extra needed queries to reduce temporal records.
        Otherwise, the loose relation would match
        """
        filters = []
        prefix = ""
        for filter_part in parts:
            prefix = f"{prefix}{filter_part.python_name}__"
            if filter_part.reverse_field is None and filter_part.field.is_loose_relation:
                # When filters join a loose relation, make sure only the active object is selected
                temp = TemporalTableQuery.from_query(
                    self.request_date,
                    self.query,
                    self.user_scopes,
                    filter_part.field.related_table,
                )
                if (range_q := temp.create_range_filter(prefix)) is not None:
                    filters.append(range_q)

        return reduce(operator.and_, filters) if filters else None

    def _translate_lookup(
        self, filter_input: FilterInput, filter_part: FilterPathPart, value: Any
    ) -> str:
        """Convert the lookup value into the Django ORM type."""
        lookup = filter_input.lookup

        # Find whether the lookup is allowed at all.
        # This prevents doing a "like" lookup on an integer/date-time field for example.
        allowed_lookups = self.get_allowed_lookups(filter_part.field)
        if lookup not in allowed_lookups:
            if not allowed_lookups:
                raise ValidationError(
                    {filter_part.name: "Field type does not support filter lookups."}
                ) from None
            else:
                possible = "', '".join(sorted(x for x in allowed_lookups if x))
                raise ValidationError(
                    {
                        filter_part.name: (
                            f"Lookup not supported: '{lookup or '(none)'}', "
                            f"supported are: '{possible}'"
                        )
                    }
                ) from None

        if filter_part.field.format == "date-time" and not isinstance(value, datetime):
            # When something different then a full datetime is given, only compare dates.
            # Otherwise, the "lte" comparison happens against 00:00:00.000 of that date,
            # instead of anything that includes that day itself.
            lookup = f"date__{lookup or 'exact'}"

        return lookup or "exact"

    def _translate_raw_value(  # noqa: C901
        self, filter_input: FilterInput, filter_part: FilterPathPart
    ):
        """Convert a filter value into the proper Python type"""
        field_schema = filter_part.field

        # Check lookup first, can be different from actual field type
        try:
            # Special cases:
            if lookup_parser := LOOKUP_PARSERS.get(filter_input.lookup):
                # Some lookups have a type that is different from the field type.
                # For example, isnull/isempty/like.
                return lookup_parser(filter_input.raw_value)
            elif field_schema.is_geo:
                # Geometry fields need a CRS to handle the input
                return str2geo(filter_input.raw_value, self.input_crs)

            if (
                field_schema.is_object or field_schema.is_array_of_objects
            ) and field_schema.related_field_ids:
                # Temporal relations (FK or M2M), e.g. ?ligtInBouwblokId=03630012095418.1
                # or ?ligtInPanden=... references their identifier as foreign key.
                return filter_input.raw_value

            if field_schema.is_array:
                items = field_schema["items"]
                parser = SCALAR_PARSERS[items.get("format") or items["type"]]
            else:
                parser = SCALAR_PARSERS[field_schema.format or field_schema.type]

            # For dates, the type is string, but the format is date/date-time.
            if filter_part.is_many or filter_input.lookup in MULTI_VALUE_LOOKUPS:
                # Value is treated as array (repeated on query string, or comma separated)
                use_split = (
                    field_schema.is_array_of_scalars or filter_input.lookup in SPLIT_VALUE_LOOKUPS
                )
                values = filter_input.split_values if use_split else filter_input.raw_values
                return [parser(v) for v in values]
            else:
                return parser(filter_input.raw_value)
        except KeyError as e:
            raise NotImplementedError(
                f"No parser defined for field {field_schema}"
                f" (type='{field_schema.type}', format='{field_schema.format}')"
            ) from e
        except (ValueError, TypeError) as e:
            raise ValidationError({field_schema.name: "Invalid value"}) from e
        except ValidationError as e:
            raise ValidationError({field_schema.name: e.detail}) from e

    @staticmethod
    def get_allowed_lookups(field_schema: DatasetFieldSchema) -> set[str]:
        """Find which field[lookup] values are possible, given the field type."""
        try:
            if field_schema.relation or field_schema.nm_relation or field_schema.is_primary:
                # The 'string' type is needed for the deprecated ?temporalRelationId=.. filter.
                field_type = "string" if field_schema.is_object else field_schema.type
                return ALLOWED_IDENTIFIER_LOOKUPS | ALLOWED_SCALAR_LOOKUPS[field_type]
            else:
                return ALLOWED_SCALAR_LOOKUPS[field_schema.format or field_schema.type]
        except KeyError:
            return set()

    @staticmethod
    def to_orm_path(
        field_path: str, table_schema: DatasetTableSchema, user_scopes: UserScopes
    ) -> str:
        """Translate a field name into a ORM path.
        This also checks whether the field is accessible according to the request scope.
        """
        parts = _parse_filter_path(field_path.split("."), table_schema, user_scopes)
        return _to_orm_path(parts)


class CompiledFilter(NamedTuple):
    """The intermediate results of a single-filter"""

    q_object: Q
    is_many: bool


def _to_orm_path(parts: list[FilterPathPart]) -> str:
    """Generate the ORM path for a path of fields."""
    names = [part.python_name for part in parts]

    if len(parts) > 1:
        # Optimize query, by avoiding a table join for foreign keys.
        # Instead of making a JOIN for "foreigntable.id", the local field can be used instead
        # by using the ORM lookup into "foreigntable_id". Note that related_field_ids is None
        # for nested tables, since those tables use a reverse relation to the parent.
        parent_part, last_part = parts[-2], parts[-1]
        if (
            not parent_part.field.is_array_of_objects  # not M2M, needs through table join
            and not parent_part.reverse_field  # not reverse field, needs join
            and (related_ids := parent_part.field.related_field_ids) is not None  # not nested
            and last_part.id in related_ids  # target field is indeed a local identifier
        ):
            # Matched identifier that also exists on the previous table, use that instead.
            # loose relation directly stores the "identifier" as name, so can just strip that.
            if last_part.field.table.is_temporal and not parent_part.field.is_loose_relation:
                names[-2] = f"{names[-2]}_{names[-1]}"
            names.pop()

    return "__".join(names)


class FilterPathPart(NamedTuple):
    """An entry in the filter path, translated to a field.
    The field and reverse field are so different in their API,
    that those fields are mentioned separately. They don't have a useful base class.
    """

    field: DatasetFieldSchema
    reverse_field: AdditionalRelationSchema | None = None
    is_many: bool = False

    @property
    def id(self):
        """Raw unmodified identifier"""
        return getattr(self.reverse_field or self.field, "id")

    @property
    def name(self):
        """Camel cased name (mirroring API fields)"""
        return getattr(self.reverse_field or self.field, "name")

    @property
    def python_name(self):
        """Snake-cased name (for ORM field names)"""
        return getattr(self.reverse_field or self.field, "python_name")


def _parse_filter_path(
    field_path: list[str], table_schema: DatasetTableSchema, user_scopes: UserScopes
) -> list[FilterPathPart]:
    """Translate the filter name into a path of schema fields.
    The result has multiple entries when the path follows over relations.
    """
    parts = []
    parent: (DatasetTableSchema | DatasetFieldSchema | None) = table_schema
    field_name = ".".join(field_path)

    last_item = len(field_path) - 1
    for i, name in enumerate(field_path):
        # When the parent is no longer set, the previous field wasn't a relation.
        if parent is None:
            raise ValidationError(f"Field '{field_name}' does not exist")

        # Find the field by name, also handle workarounds for relation ID's.
        filter_part = _get_field_by_id(parent, name, is_last=(i == last_item))
        if filter_part is None:
            raise ValidationError(f"Field '{field_name}' does not exist")

        # forward relation
        field = filter_part.field
        check_filter_field_access(field_name, field, user_scopes)

        if filter_part.reverse_field is not None:
            parent = filter_part.reverse_field.related_table
        elif field.relation or field.nm_relation:
            parent = field.related_table
        elif field.subfields:
            # For sub-fields, treat this as a nested table
            parent = field
        else:
            parent = None

        parts.append(filter_part)

    return parts


def _get_field_by_id(  # noqa: C901
    parent: (DatasetTableSchema | DatasetFieldSchema | None), name: str, is_last: bool
) -> FilterPathPart | None:
    """Find the field in the Amsterdam schema.
    Handle workarounds for foreignkey ID fields that were previously exposed.
    """
    field = None
    try:
        field = parent.get_field_by_id(name)
    except SchemaObjectNotFound:
        # Backwards compatibility: allow filtering on the "FOREIGNKEY_id" field,
        # that was exposed in the API. This should only happen when the "Id" suffix is
        # truly a foreign key. (So avoid "streetId.number=..." or "anyfieldId=...").
        if name.endswith("Id") and is_last:
            try:
                field = parent.get_field_by_id(name[:-2])
            except SchemaObjectNotFound:
                pass
            if not field.relation:
                field = None  # only allow relations for "Id" suffix.

    if field is not None:
        # Found regular field, or forward relation
        return FilterPathPart(field=field, is_many=field.is_array)

    try:
        additional_relation = parent.get_additional_relation_by_id(name)
    except SchemaObjectNotFound:
        return None
    else:
        # The additional relation name is used as ORM path to navigate over the relation.
        # Yet when directly filtering, the value/lookup should work directly
        # against the primary key of the reverse table (hence field is also resolved here)
        return FilterPathPart(
            field=additional_relation.related_table.identifier_fields[0],
            reverse_field=additional_relation,
            is_many=True,
        )
