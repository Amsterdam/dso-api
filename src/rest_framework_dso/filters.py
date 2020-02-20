"""API filtering.

This implements the filtering and ordering spec.
DSO 1.1 Spec: "2.6.6 Filteren, sorteren en zoeken"
"""
from typing import Type

from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import lookups
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, filters
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework_gis.filters import GeometryFilter

__all__ = [
    "DSOFilterSet",
    "DSOFilterSetBackend",
    "DSOOrderingFilter",
]


@models.CharField.register_lookup
@models.TextField.register_lookup
class Wildcard(lookups.Lookup):
    """Allow fieldname__wildcard=... lookups in querysets."""

    lookup_name = "wildcard"

    def as_sql(self, compiler, connection):
        """Generate the required SQL."""
        # lhs = "table"."field"
        # rhs = %s
        # lhs_params = []
        # lhs_params = ["prep-value"]
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f"{lhs} LIKE {rhs}", lhs_params + rhs_params

    def get_db_prep_lookup(self, value, connection):
        """Apply the wildcard logic to the right-hand-side value"""
        value = (
            value
            # Escape % and _ first.
            # Not using r"\" here as that is a syntax error.
            .replace("\\", "\\\\")
            .replace("%", r"\%")
            .replace("_", r"\_")
            # Replace wildcard chars with SQL LIKE logic
            .replace("*", "%")
            .replace("?", "_")
        )
        return "%s", [value]


class SimpleDateTimeFilter(filters.DateFilter):
    """Filter a DateTime field using a date only. Ignore the time component."""

    # TODO: implement before/after syntax.
    # Currently this is not implemented, as it's unclear what syntax is preferred:
    # - ?datefield=lt:...
    # - ?datefield__lt=...
    # - ?datefield_before=...
    # - ?datefield.before=...
    # - ?datefield[before]=...

    def filter(self, qs, value):
        """Implement filtering on single day for a 'datetime' field."""
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()

        return self.get_method(qs)(**{f"{self.field_name}__date": value})


class DSOFilterSet(FilterSet):
    """Base class to create filter sets.

    The 'FILTER_DEFAULTS' field defines how fields are constructed.
    Usage in views::

        class View(APIView):
            filter_backends = [filters.DSOFilterSetBackend]
            filterset_class = ... # subclass of DSOFilterSetBackend
    """

    FILTER_DEFAULTS = {
        **FilterSet.FILTER_DEFAULTS,
        # Unlike **GeoFilterSet.GEOFILTER_FOR_DBFIELD_DEFAULTS,
        # also enforce the geom_type for the input:
        models.CharField: {
            "filter_class": filters.CharFilter,
            "extra": lambda field: {"lookup_expr": "wildcard"},
        },
        models.TextField: {
            "filter_class": filters.CharFilter,
            "extra": lambda field: {"lookup_expr": "wildcard"},
        },
        models.DateTimeField: {
            # Only allow filtering on dates for now, ignore time component.
            "filter_class": SimpleDateTimeFilter,
        },
        gis_models.GeometryField: {
            "filter_class": GeometryFilter,
            "extra": lambda field: {"geom_type": field.geom_type},
        },
    }

    FILTER_HELP_TEXT = {
        filters.BooleanFilter: "true | false",
        filters.CharFilter: "text",
        filters.DateFilter: "yyyy-mm-dd",
        SimpleDateTimeFilter: "yyyy-mm-dd",
        filters.IsoDateTimeFilter: "yyyy-mm-ddThh:mm[:ss[.ms]]",
        filters.ModelChoiceFilter: "id",
        GeometryFilter: "GeoJSON | GEOMETRY(...)",
    }

    @classmethod
    def filter_for_lookup(cls, field, lookup_type):
        """Generate the 'help_text' if the model field doesn't present this.
        This data is shown in the Swagger docs, and browsable API.
        """
        filter_class, params = super().filter_for_lookup(field, lookup_type)
        if "help_text" not in params:
            params["help_text"] = cls.get_filter_help_text(filter_class, params)
        return filter_class, params

    @classmethod
    def get_filter_help_text(cls, filter_class: Type[filters.Filter], params) -> str:
        """Get a brief default description for a filter in the API docs"""
        if issubclass(filter_class, GeometryFilter):
            geom_type = params.get("geom_type", "GEOMETRY")
            return f"GeoJSON | {geom_type}(x y ...)"

        try:
            return cls.FILTER_HELP_TEXT[filter_class]
        except KeyError:
            return filter_class.__name__.replace("Filter", "").lower()


class DSOFilterSetBackend(DjangoFilterBackend):
    """DSF fields filter.

    This loads the filterset logic of django-filter.
    Usage in views::

        class View(APIView):
            filter_backends = [filters.DSOFilterSetBackend]
            filterset_class = ... # subclass of DSOFilterSetBackend

    The ``filterset_class`` defines how each querystring field is parsed
    and processed.
    """

    def to_html(self, request, queryset, view):
        """See https://github.com/tomchristie/django-rest-framework/issues/3766.

        This prevents DRF from generating the filter dropdowns
        (which can be HUGE in our case)
        """
        return ""


class DSOOrderingFilter(OrderingFilter):
    """DRF Ordering filter, following the DSO spec.
    Usage in views::

        class View(APIView):
            filter_backends = [filters.DSOOrderingFilter]

    This adds an ``?sorteer=<fieldname>,-<desc-fieldname>`` option to the view.
    On the view, an ``view.ordering_fields`` attribute may limit which fields
    can be used in the sorting. By default, it's all serializer fields.
    """

    ordering_param = "sorteer"  # ugh.

    def remove_invalid_fields(self, queryset, fields, view, request):
        """Raise errors for invalid parameters instead of silently dropping them."""
        cleaned = super().remove_invalid_fields(queryset, fields, view, request)
        if cleaned != fields:
            invalid = ", ".join(sorted(set(fields).difference(cleaned)))
            raise ValidationError(f"Invalid sort fields: {invalid}", code="order-by")
        return cleaned
