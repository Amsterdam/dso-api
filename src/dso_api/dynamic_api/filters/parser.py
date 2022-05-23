"""The engine for filtering from the query-string.

This translates a query-string into ORM lookups using the Amsterdam Schema definitions.
"""
from __future__ import annotations

import operator
import re
from datetime import datetime
from functools import reduce
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.models import Q
from django.utils.datastructures import MultiValueDict
from gisserver.geometries import CRS
from rest_framework.exceptions import PermissionDenied, ValidationError
from schematools.contrib.django.models import DynamicModel
from schematools.exceptions import SchemaObjectNotFound
from schematools.permissions import UserScopes
from schematools.types import DatasetFieldSchema, DatasetTableSchema
from schematools.utils import to_snake_case

from .values import str2bool, str2geo, str2isodate, str2number, str2time

# Allow notations: field.subfield[lookup]
RE_KEY = re.compile(r"\A(?P<path>[\w\d_-]+(?:\.[\w\d_-]+)*)(?:\[(?P<lookup>[a-z0-9A-Z_-]+)])?\Z")

# Lookups that have specific value types:
LOOKUP_PARSERS = {
    "isnull": str2bool,
    "isempty": str2bool,
    "like": str,  # e.g. uri is parsed as string for like.
}

MULTI_VALUE_LOOKUPS = {"not": operator.and_}
SPLIT_VALUE_LOOKUPS = {"in"}

SCALAR_PARSERS = {
    "boolean": str2bool,
    "string": lambda f: f,
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

ALLOWED_SCALAR_LOOKUPS = {
    "integer": _comparison_lookups,
    "number": _comparison_lookups,
    "string": _string_lookups,
    "array": {"contains"},
    "object": set(),
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
        self.raw_values = raw_values

    @classmethod
    def from_parameter(cls, key: str, raw_values: list[str]) -> FilterInput:
        """Construct this parsed class from a single query parameter."""
        match = RE_KEY.match(key)
        if match is None:
            raise ValidationError(f"Invalid filter: {key}")

        return cls(
            key=key,
            path=match.group("path").split("."),
            lookup=match.group("lookup"),
            raw_values=raw_values,
        )

    def __str__(self):
        return self.key

    @property
    def raw_value(self) -> str:
        """Provide access to a single value when the filter expects this."""
        return self.raw_values[0]


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

    def __init__(self, user_scopes: UserScopes, query: MultiValueDict, input_crs: CRS):
        self.user_scopes = user_scopes
        self.query = query
        self.input_crs = input_crs
        self.filter_inputs = self._parse_filters(query)

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
        q = self.get_q(queryset.model)
        if q is not None:
            try:
                queryset = queryset.filter(q)
            except DjangoValidationError as e:
                raise ValidationError(list(e)) from e

        return queryset

    def get_q(self, model: type[DynamicModel]) -> models.Q | None:
        qs = []
        table_schema = model.table_schema()
        for filter_input in self.filter_inputs:
            if table_schema.temporal and filter_input.key in table_schema.temporal.dimensions:
                # Skip handling of temporal fields, is handled elsewhere.
                continue

            q_obj = self._get_field_q(table_schema, filter_input)
            qs.append(q_obj)

        return reduce(operator.and_, qs) if qs else None

    def _get_field_q(
        self, table_schema: DatasetTableSchema, filter_input: FilterInput
    ) -> models.Q:
        """Build the Q() object for a single filter"""
        fields = parse_filter_path(filter_input.path, table_schema, self.user_scopes)
        orm_path = _to_orm_path(fields)

        value = self._translate_raw_value(filter_input, fields[-1])
        lookup = self._translate_lookup(filter_input, fields[-1], value)
        q_path = f"{orm_path}__{lookup}"

        operator = MULTI_VALUE_LOOKUPS.get(filter_input.lookup)
        if operator is not None:
            # for [not] lookup: field != 1 AND field != 2
            return reduce(operator, (Q(**{q_path: v}) for v in value))
        else:
            return Q(**{q_path: value})

    def _translate_lookup(
        self, filter_input: FilterInput, field_schema: DatasetFieldSchema, value: Any
    ):
        """Convert the lookup value into the Django ORM type."""
        lookup = filter_input.lookup

        # Find whether the lookup is allowed at all.
        # This prevents doing a "like" lookup on an integer/date-time field for example.
        allowed_lookups = self.get_allowed_lookups(field_schema)
        if lookup not in allowed_lookups:
            possible = ", ".join(sorted(x for x in allowed_lookups if x))
            raise ValidationError(
                {
                    field_schema.name: (
                        f"Lookup not supported: {lookup or '(none)'}, supported are: {possible}"
                    )
                }
            ) from None

        if field_schema.format == "date-time" and not isinstance(value, datetime):
            # When something different then a full datetime is given, only compare dates.
            # Otherwise, the "lte" comparison happens against 00:00:00.000 of that date,
            # instead of anything that includes that day itself.
            lookup = f"date__{lookup or 'exact'}"

        return lookup or "exact"

    def _translate_raw_value(  # noqa: C901
        self, filter_input: FilterInput, field_schema: DatasetFieldSchema
    ):
        """Convert a filter value into the proper Python type"""
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

            target_schema = field_schema
            if field_schema.is_object and field_schema.related_field_ids:
                # Temporal relations, e.g. ?ligtInBouwblokId=03630012095418.1
                # that references their identifier stored as foreign key.
                return filter_input.raw_value

            # For dates, the type is string, but the format is date/date-time.
            parser = SCALAR_PARSERS[target_schema.format or target_schema.type]
            if field_schema.is_array or filter_input.lookup in MULTI_VALUE_LOOKUPS:
                # Value is treated as array (repeated on query string)
                return [parser(v) for v in filter_input.raw_values]
            elif filter_input.lookup in SPLIT_VALUE_LOOKUPS:
                # Value is comma separated (field[in]=...)
                return [parser(v) for v in filter_input.raw_value.split(",")]
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
        fields = parse_filter_path(field_path.split("."), table_schema, user_scopes)
        return _to_orm_path(fields)


def _to_orm_path(fields: list[DatasetFieldSchema]) -> str:
    """Generate the ORM path for a path of fields."""
    names = [to_snake_case(field.name) for field in fields]

    if len(fields) > 1:
        # When spanning relations, check whether this can be optimized.
        # Instead of making a JOIN for "foreigntable.id", the local field can be used instead
        # by using the ORM lookup into "foreigntable_id". Note that related_field_ids is None
        # for nested tables, since those tables use a reverse relation to the parent.
        related_ids = fields[-2].related_field_ids
        if related_ids is not None and fields[-1].name in related_ids:
            # Matched identifier that also exists on the previous table, use that instead.
            # loose relation directly stores the "identifier" as name, so can just strip that.
            if not fields[-2].is_loose_relation:
                names[-2] = f"{names[-2]}_{names[-1]}"
            names.pop()

    return "__".join(names)


def parse_filter_path(
    field_path: list[str], table_schema: DatasetTableSchema, user_scopes: UserScopes
) -> list[DatasetFieldSchema]:
    """Translate the filter name into a path of schema fields.
    The result has multiple entries when the path follows over relations.
    """
    fields = []
    parent: (DatasetTableSchema | DatasetFieldSchema | None) = table_schema
    field_name = ".".join(field_path)

    last_item = len(field_path) - 1
    for i, name in enumerate(field_path):
        # When the parent is no longer set, the previous field wasn't a relation.
        if parent is None:
            raise ValidationError(f"Field does not exist: {field_name}")

        # Find the field by name, also handle workarounds for relation ID's.
        field = _get_field_by_id(parent, name, is_last=(i == last_item))
        if field is None:
            raise ValidationError(f"Field does not exist: {field_name}")

        if not user_scopes.has_field_access(field):
            raise PermissionDenied(f"Access denied to filter on: {field_name}") from None

        fields.append(field)

        if field.relation or field.nm_relation:
            # For nesting, look into the next table
            parent = field.related_table

            if (
                field.is_loose_relation
                and i < last_item
                and not (
                    i + 1 == last_item and field_path[last_item] == field.related_field_ids[0]
                )
            ):
                # No support for looserelation__field=.. in the ORM yet.
                raise ValidationError(
                    {
                        field_name: (
                            f"Filtering nested fields of '{field.name}' is not yet supported,"
                            f" except for the primary key ({field.related_field_ids[0]})."
                        )
                    }
                )
        elif field.subfields:
            # For sub-fields, treat this as a nested table
            parent = field
        else:
            parent = None

    return fields


def _get_field_by_id(
    parent: (DatasetTableSchema | DatasetFieldSchema | None), name: str, is_last: bool
) -> DatasetFieldSchema | None:
    """Find the field in the Amsterdam schema.
    Handle workarounds for foreignkey ID fields that were previously exposed.
    """
    try:
        return parent.get_field_by_id(name)
    except SchemaObjectNotFound:
        # Backwards compatibility: allow filtering on the "FOREIGNKEY_id" field,
        # that was exposed in the API. This should only happen when the "Id" suffix is
        # truly a foreign key. (So avoid "streetId.number=..." or "anyfieldId=...").
        if name.endswith("Id") and is_last:
            try:
                field = parent.get_field_by_id(name[:-2])
            except SchemaObjectNotFound:
                return None
            if field.relation:
                return field

    return None
