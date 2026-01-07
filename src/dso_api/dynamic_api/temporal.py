"""Extra functionality to handle temporality.

This includes things like:
- Only retrieve certain historical versions of an object.
- Reduce querysets/get_object logic
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from django.db import models
from django.db.models import Q
from django.utils.timezone import get_current_timezone, now
from more_itertools import first
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from schematools.naming import to_snake_case
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema, TemporalDimensionFields

from dso_api.dynamic_api.permissions import check_filter_field_access


class TemporalTableQuery:
    """The temporal query from the request, mapped to the current table."""

    table_schema: DatasetTableSchema
    is_versioned: bool

    #: Which historical version is requested.
    version_field: str | None = None
    version_value: str | None = None

    #: Which date is requested
    slice_dimension: str | None = None
    slice_value: Literal["*"] | date | datetime | None = None
    slice_range_fields: TemporalDimensionFields | None = None

    def __bool__(self):
        return self.is_versioned

    @classmethod
    def from_request(
        cls, request: Request, table_schema: DatasetTableSchema, pk: str | None = None
    ):
        """Construct the object using all information found in the request object."""
        request_date = get_request_date(request)
        return cls.from_query(request_date, request.GET, request.user_scopes, table_schema, pk)

    @classmethod
    def from_query(
        cls,
        request_date: datetime,
        query: dict[str, str],
        user_scopes: UserScopes,
        table_schema: DatasetTableSchema,
        pk: str | None = None,
    ):
        """Construct the object without having to use a request object."""
        if table_schema.temporal is None:
            return cls(table_schema=table_schema)
        else:
            # See if a filter is made on a specific version
            version_field = table_schema.temporal.identifier_field  # e.g. "volgnummer"
            version_value = query.get(version_field.name, None)
            if not version_value and pk is not None and "." in pk:
                version_value = pk.split(".")[1]
            if version_value:
                check_filter_field_access(version_field.id, version_field, user_scopes)

            # See if a filter is done on a particular point in time (e.g. ?geldigOp=yyyy-mm-dd)
            slice_dimension = None
            slice_value = None
            for dimension, slice_range_fields in table_schema.temporal.dimensions.items():
                if date_value := query.get(dimension):
                    if slice_dimension is not None:  # pragma: no cover
                        # There is basically no point in combining temporal dimensions,
                        # and if this is really a requested feature, it can be implemented.
                        raise ValidationError(
                            f"Can't filter on both '{slice_dimension}'"
                            f" and '{dimension}' at the same time!"
                        ) from None

                    slice_dimension = dimension  # e.g. geldigOp
                    slice_value = cls._parse_date(dimension, date_value)

                    # Check whether the user may filter on the temporal dimension.
                    for range_field in slice_range_fields:
                        check_filter_field_access(slice_dimension, range_field, user_scopes)

            return cls(
                table_schema=table_schema,
                #: Which historical version is requested.
                version_value=version_value,
                #: Which date is requested
                slice_dimension=slice_dimension,
                slice_value=slice_value or request_date,
            )

    def __init__(
        self,
        table_schema: DatasetTableSchema,
        current_date: datetime | None = None,
        #: Which historical version is requested.
        version_value: str | None = None,
        #: Which date is requested
        slice_dimension: str | None = None,
        slice_value: Literal["*"] | date | datetime | None = None,
    ):
        """Direct initialization, allowing to perform unit testing."""
        self.table_schema = table_schema
        self.is_versioned = table_schema.temporal is not None
        self.version_value = version_value
        self.slice_dimension = slice_dimension
        self.slice_value = slice_value or current_date

    @staticmethod
    def _parse_date(dimension: str, value: str) -> Literal["*"] | date | datetime:
        """Parse and validate the received date"""
        if value == "*":
            return "*"

        try:
            if "T" in value or " " in value:
                # Add timezone if needed.
                val = datetime.fromisoformat(value)
                return val.replace(tzinfo=get_current_timezone()) if val.tzinfo is None else val
            else:
                return date.fromisoformat(value)
        except ValueError:
            raise ValidationError(
                f"Invalid date or date-time format for '{dimension}' parameter!"
            ) from None

    def filter_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply temporal filtering to the queryset, based on the request parameters."""
        if queryset.model.table_schema() != self.table_schema:
            raise ValueError("QuerySet model type does not match")

        return self._filter_queryset(queryset, prefix="")

    def create_range_filter(self, prefix: str) -> Q:
        """Create a simple Q-object for filtering on a temporal range."""
        if not self.is_versioned or self.slice_value == "*":
            return Q()
        else:
            return self._compile_range_query(prefix)[0]

    def filter_m2m_queryset(self, queryset: models.QuerySet, relation: models.ForeignKey):
        """Apply temporal filtering to a queryset,
        using the model that the relation points to.

        This is useful for filtering though-tables,
        where only the target relation has temporal data.
        """
        if relation.related_model.table_schema() != self.table_schema:
            raise ValueError("QuerySet model type does not match")

        return self._filter_queryset(queryset, prefix=f"{relation.name}__")

    def _filter_queryset(self, queryset: models.QuerySet, prefix: str):
        """Internal logic to filter a queryset on request-parameters for a temporal slice."""
        if not self.is_versioned or self.slice_value == "*":
            # allow this method to be called unconditionally on objects,
            # and allow ?geldigOp=* to return all data
            return queryset

        identifier_set = set(self.table_schema.identifier)  # from ["identificatie", "volgnummer"]
        if len(identifier_set) != 2:
            raise RuntimeError("Schema does not implement usable temporal dimensions")
        sequence_name = self.table_schema.temporal.identifier
        # Order of identifier_set is not guaranteed, so we explicitly remove the sequence_name
        identifier = to_snake_case(list(identifier_set - {sequence_name})[0])

        try:
            range_q, main_ordering = self._compile_range_query(prefix)
            return queryset.filter(range_q).order_by(f"{prefix}{identifier}", main_ordering)
        except RuntimeError:
            # Last attempt to get only the current temporal record; order by sequence.
            # does SELECT DISTINCT ON(identifier) ... ORDER BY identifier, sequence DESC
            # Alternative would be something like `HAVING sequence = MAX(SELECT sequence FROM ..)`
            return queryset.distinct(
                *queryset.query.distinct_fields, f"{prefix}{identifier}"
            ).order_by(f"{prefix}{identifier}", f"-{prefix}{sequence_name}")

    def _compile_range_query(self, prefix: str) -> tuple[Q, str]:
        # Either take a given ?geldigOp=yyyy-mm-dd OR ?geldigOp=NOW()
        if (range_fields := self._get_range_fields()) is None:
            raise RuntimeError("Schema does not implement usable temporal dimensions")

        # start <= value AND (end IS NULL OR value < end)
        start = f"{prefix}{range_fields.start.python_name}"
        end = f"{prefix}{range_fields.end.python_name}"
        return (
            Q(**{f"{start}__lte": self.slice_value})
            & (Q(**{f"{end}__isnull": True}) | Q(**{f"{end}__gt": self.slice_value})),
            f"-{start}",
        )

    def _get_range_fields(self) -> TemporalDimensionFields | None:
        """Tell what the default fields would be to filter temporal objects."""
        dimensions = self.table_schema.temporal.dimensions
        if self.slice_dimension:
            # Query takes a specific dimension
            return dimensions[self.slice_dimension]
        else:
            # Find what a good default would be (typically called geldigOp).
            return dimensions.get("geldigOp") or first(dimensions.values(), None)

    @property
    def url_parameters(self) -> dict[str, str]:
        if self.slice_dimension:
            # e.g. ?geldigOp=...
            url_value = "*" if self.slice_value == "*" else self.slice_value.isoformat()
            return {self.slice_dimension: url_value}
        else:
            return {}


def get_request_date(request: Request) -> datetime:
    """Find the temporal query date, associated with the request object."""
    try:
        # Make sure all queries use the exact same now, not seconds/milliseconds apart.
        return request._now
    except AttributeError:
        request._now = now()
        return request._now


def filter_temporal_slice(request, queryset: models.QuerySet) -> models.QuerySet:
    """Make sure a queryset will only return the requested temporal date."""
    table_schema = queryset.model.table_schema()
    if not table_schema.temporal:
        return queryset
    else:
        return TemporalTableQuery.from_request(request, table_schema).filter_queryset(queryset)


def filter_temporal_m2m_slice(
    request, queryset: models.QuerySet, relation: models.ForeignKey
) -> models.QuerySet:
    """Fiter a queryset, but using the temporality of the table references by the foreign key.
    This is only useful for M2M relations, where the entries of the through-table
    should be filtered, and the target relation should be filtered too.
    """
    related_table_schema = relation.related_model.table_schema()
    if not related_table_schema.temporal:
        return queryset
    else:
        table_query = TemporalTableQuery.from_request(request, related_table_schema)
        return table_query.filter_m2m_queryset(queryset, relation)
