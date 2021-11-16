"""Additional filter classes to implement the DSO requirements."""
import operator
from datetime import datetime
from functools import reduce

from django.db.models import Q
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import filters

from .fields import FlexDateTimeField, ModelIdChoiceField
from .forms import CharArrayField, MultipleValueField


class ExactCharFilter(filters.CharFilter):
    """Explicitly naming filters.CharFilter the ExactCharFilter"""

    pass


class CharArrayFilter(filters.BaseCSVFilter, filters.CharFilter):
    """Comma Separated Array filter"""

    base_field_class = CharArrayField


class WildcardCharFilter(filters.CharFilter):
    """Char filter that uses the 'wildcard' lookup by default."""

    def __init__(self, field_name=None, lookup_expr="exact", **kwargs):
        # Make sure that only the "__exact" lookup is translated into a
        # wildcard lookup. Passing 'lookup_expr' in FILTER_DEFAULTS's "extra"
        # field overrides all chosen lookup types.
        if lookup_expr == "exact":
            lookup_expr = "wildcard"
        super().__init__(field_name, lookup_expr, **kwargs)


class FlexDateTimeFilter(filters.IsoDateTimeFilter):
    """Flexible input parsing for a datetime field, allowing dates only."""

    field_class = FlexDateTimeField

    def filter(self, qs, value):
        """Implement filtering on single day for a 'datetime' field."""
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()

        if not isinstance(value, datetime):
            # When something different then a full datetime is given, only compare dates.
            # Otherwise, the "lte" comparison happens against 00:00:00.000 of that date,
            # instead of anything that includes that day itself.
            lookup = f"date__{self.lookup_expr}"
        else:
            lookup = self.lookup_expr

        return self.get_method(qs)(**{f"{self.field_name}__{lookup}": value})


class MultipleValueFilter(filters.Filter):
    """Filter that is the AND or OR of several filters on the same field.

    This is used to construct filters such as ?field[not]=x&field[not]=y.
    """

    field_class = MultipleValueField
    OPERATORS = {
        "AND": operator.and_,
        "OR": operator.or_,
    }

    def __init__(self, value_filter: filters.Filter, operator="AND"):
        super().__init__(
            # Copy settings from wrapped field
            field_name=value_filter.field_name,
            lookup_expr=value_filter.lookup_expr,
            label=value_filter._label,
            method=value_filter._method,
            distinct=value_filter.distinct,
            exclude=value_filter.exclude,
            **value_filter.extra,  # includes 'required'
            # Pass as **extra to the widget:
            subfield=value_filter.field,
        )
        self.value_filter = value_filter
        self.operator = operator

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()

        lookup = f"{self.field_name}__{self.lookup_expr}"
        op = self.OPERATORS[self.operator]
        q = reduce(op, (Q(**{lookup: subvalue}) for subvalue in value))
        return self.get_method(qs)(q)


class ModelIdChoiceFilter(filters.ModelChoiceFilter):
    """Improved choice filter for IN queries.

    Note that the django-filter's ``BaseFilterSet.filter_for_lookup()``
    subclasses this class as ``ConcreteInFilter(BaseInFilter, filter_class)``
    for lookup_type="in".
    """

    field_class = ModelIdChoiceField
