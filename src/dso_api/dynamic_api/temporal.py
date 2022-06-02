"""Extra functionality to handle temporality.

This includes things like:
- Only retrieve certain historical versions of an object.
- Reduce querysets/get_object logic
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, Union

from django.db import models
from django.db.models import Q
from django.utils.timezone import make_aware, now
from more_itertools import first
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from schematools.types import DatasetTableSchema, TemporalDimensionFields
from schematools.utils import to_snake_case

from dso_api.dynamic_api.permissions import check_filter_field_access


class TemporalTableQuery:
    """The temporal query from the request, mapped to the current table."""

    table_schema: DatasetTableSchema
    is_versioned: bool

    #: Which historical version is requested.
    version_field: Optional[str] = None
    version_value: Optional[str] = None

    #: Which date is requested
    slice_dimension: Optional[str] = None
    slice_value: Optional[Union[Literal["*"], date, datetime]] = None
    slice_range_fields: Optional[TemporalDimensionFields] = None

    def __bool__(self):
        return self.is_versioned

    def __init__(self, request: Request, table_schema: DatasetTableSchema):
        temporal = table_schema.temporal
        self.table_schema = table_schema
        self.is_versioned = temporal is not None

        if temporal is not None:
            # See if a filter is made on a specific version
            self.version_field = temporal.identifier  # e.g. "volgnummer"
            self.version_value = request.GET.get(self.version_field, None)

            if self.version_value:
                field = self.table_schema.get_field_by_id(self.version_field)
                check_filter_field_access(self.version_field, field, request.user_scopes)

            # See if a filter is done on a particular point in time (e.g. ?geldigOp=yyyy-mm-dd)
            for dimension, fields in temporal.dimensions.items():
                if date_value := request.GET.get(dimension):
                    self.slice_dimension = dimension  # e.g. geldigOp
                    self.slice_value = self._parse_date(dimension, date_value)
                    self.slice_range_fields = fields

                    # Check whether the user may filter on the temporal dimension.
                    for name in self.slice_range_fields:
                        field = self.table_schema.get_field_by_id(name)
                        check_filter_field_access(self.slice_dimension, field, request.user_scopes)

    def _parse_date(self, dimension: str, value: str) -> Union[Literal["*"], date, datetime]:
        """Parse and validate the received date"""
        if value == "*":
            return "*"

        try:
            if "T" in value or " " in value:
                return make_aware(datetime.fromisoformat(value))
            else:
                return date.fromisoformat(value)
        except ValueError:
            raise ValidationError(
                f"Invalid date or date-time format for '{dimension}' parameter!"
            ) from None

    def filter_object_version(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply an object-level filter such as "?volgnummer=...".
        This should only be called for the top-level object.
        """
        if queryset.model.table_schema() != self.table_schema:
            raise ValueError("QuerySet model type does not match")

        if not self.is_versioned:
            return queryset
        elif self.version_value is None:
            return self.filter_queryset(queryset)
        else:
            return queryset.filter(**{self.version_field: self.version_value})

    def filter_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply temporal filtering to the queryset, based on the request parameters."""
        if queryset.model.table_schema() != self.table_schema:
            raise ValueError("QuerySet model type does not match")

        return self._filter_queryset(queryset, prefix="")

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

        # Either take a given ?geldigOp=yyyy-mm-dd OR ?geldigOp=NOW()
        slice_value = self.slice_value or now()
        range_fields = self.slice_range_fields or self.default_range_fields

        if range_fields is not None:
            # start <= value AND (end IS NULL OR value < end)
            start, end = map(to_snake_case, range_fields)
            return queryset.filter(
                Q(**{f"{prefix}{start}__lte": slice_value})
                & (
                    Q(**{f"{prefix}{end}__isnull": True})
                    | Q(**{f"{prefix}{end}__gt": slice_value})
                )
            ).order_by(f"-{prefix}{start}")
        else:
            # Last attempt to get only the current temporal record; order by sequence.
            # does SELECT DISTINCT ON(identifier) ... ORDER BY identifier, sequence DESC
            # Alternative would be something like `HAVING sequence = MAX(SELECT sequence FROM ..)`
            identifier = self.table_schema.identifier[0]  # from ["identificatie", "volgnummer"]
            sequence_name = self.table_schema.temporal.identifier
            return queryset.distinct(
                *queryset.query.distinct_fields, f"{prefix}{identifier}"
            ).order_by(f"{prefix}{identifier}", f"-{prefix}{sequence_name}")

    @property
    def default_range_fields(self) -> Optional[TemporalDimensionFields]:
        """Tell what the default fields would be to filter temporal objects."""
        dimensions = self.table_schema.temporal.dimensions
        return dimensions.get("geldigOp") or first(dimensions.values(), None)

    @property
    def url_parameters(self) -> dict[str, str]:
        if self.slice_dimension:
            # e.g. ?geldigOp=...
            url_value = "*" if self.slice_value == "*" else self.slice_value.isoformat()
            return {self.slice_dimension: url_value}
        else:
            return {}


def filter_temporal_slice(request, queryset: models.QuerySet) -> models.QuerySet:
    """Make sure a queryset will only return the requested temporal date."""
    table_schema = queryset.model.table_schema()
    if not table_schema.temporal:
        return queryset
    else:
        return TemporalTableQuery(request, table_schema).filter_queryset(queryset)


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
        table_query = TemporalTableQuery(request, related_table_schema)
        return table_query.filter_m2m_queryset(queryset, relation)
