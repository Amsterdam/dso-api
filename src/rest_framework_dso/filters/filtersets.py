from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.fields.array import ArrayField
from django.db import models
from django.db.models.fields import BigIntegerField
from django_filters.filters import NumberFilter
from django_filters.rest_framework import FilterSet, filters
from django_postgres_unlimited_varchar import UnlimitedCharField
from rest_framework_gis.filters import GeometryFilter

from .filters import (
    CharArrayFilter,
    ExactCharFilter,
    FlexDateTimeFilter,
    ModelIdChoiceFilter,
    MultipleValueFilter,
    WildcardCharFilter,
)


class DSOFilterSet(FilterSet):
    """Base class to create filter sets.

    The ``FILTER_DEFAULTS`` attribute defines how fields are constructed;
    it translates the Django model fields to proper filter class.
    Usage in views::

        class MyFilterSet(DSOFilterBackend):
            class Meta:
                model = MyModel
                fields = {
                    'field1': ['exact', 'gt', 'lt', 'lte'],
                    'field2': ['exact'],
                }


        class View(GenericAPIView):
            filter_backends = [filters.DSOFilterBackend]
            filterset_class = MyFilterSet
    """

    FILTER_DEFAULTS = {
        **FilterSet.FILTER_DEFAULTS,
        # Unlike **GeoFilterSet.GEOFILTER_FOR_DBFIELD_DEFAULTS,
        # also enforce the geom_type for the input:
        models.CharField: {"filter_class": ExactCharFilter},
        models.TextField: {"filter_class": ExactCharFilter},
        models.DateTimeField: {
            # Only allow filtering on dates for now, ignore time component.
            "filter_class": FlexDateTimeFilter,
        },
        gis_models.GeometryField: {
            "filter_class": GeometryFilter,
        },
        # Unlike the base class, don't enforce ID value checking on foreign keys
        models.ForeignKey: {
            **FilterSet.FILTER_DEFAULTS[models.ForeignKey],
            "filter_class": ModelIdChoiceFilter,
        },
        models.OneToOneField: {
            **FilterSet.FILTER_DEFAULTS[models.OneToOneField],
            "filter_class": ModelIdChoiceFilter,
        },
        models.OneToOneRel: {
            **FilterSet.FILTER_DEFAULTS[models.OneToOneRel],
            "filter_class": ModelIdChoiceFilter,
        },
        UnlimitedCharField: {"filter_class": ExactCharFilter},
        ArrayField: {"filter_class": CharArrayFilter},
        BigIntegerField: {"filter_class": NumberFilter},
    }

    LOOKUP_HELP_TEXT = {
        "like": "text with wildcards",
        "isempty": "true | false",
        "isnull": "true | false",
    }

    FILTER_HELP_TEXT = {
        filters.BooleanFilter: "true | false",
        filters.CharFilter: "text",
        filters.NumberFilter: "number",
        filters.DateFilter: "yyyy-mm-dd",
        filters.TimeFilter: "hh:mm[:ss[.ms]]",
        filters.IsoDateTimeFilter: "yyyy-mm-ddThh:mm[:ss[.ms]]",
        FlexDateTimeFilter: "yyyy-mm-dd or yyyy-mm-ddThh:mm[:ss[.ms]]",
        filters.ModelChoiceFilter: "id",
        filters.ModelMultipleChoiceFilter: "id",
        ExactCharFilter: "text (exact match)",
        ModelIdChoiceFilter: "id",
        GeometryFilter: "GeoJSON | GEOMETRY(...)",
        CharArrayFilter: "Comma separated list of strings",
        WildcardCharFilter: "text with wildcards",
    }

    @classmethod
    def get_filter_name(cls, field_name, lookup_expr):
        """Generate the lookup expression syntax field[..]=..."""
        if lookup_expr == "exact":
            return field_name
        else:
            return f"{field_name}[{lookup_expr}]"

    @classmethod
    def filter_for_field(cls, field, field_name, lookup_expr="exact"):
        """Wrap the NOT filter in a multiple selector"""
        filter_instance = super().filter_for_field(field, field_name, lookup_expr=lookup_expr)

        if lookup_expr == "not":
            # Allow &field[not]=...&field[not]=...
            filter_instance = MultipleValueFilter(filter_instance)

        return filter_instance

    @classmethod
    def filter_for_lookup(cls, field, lookup_type):
        """Generate the 'label' if the model field doesn't present this.
        This data is shown in the Swagger docs, and browsable API.
        """
        filter_class, params = super().filter_for_lookup(field, lookup_type)
        if lookup_type == "isempty":
            filter_class = filters.BooleanFilter
        if filter_class is not None and "label" not in params:
            # description for swagger:
            params["label"] = cls.get_filter_help_text(filter_class, lookup_type, params)

        return filter_class, params

    @classmethod
    def get_filter_help_text(cls, filter_class: type[filters.Filter], lookup_type, params) -> str:
        """Get a brief default description for a filter in the API docs"""
        if issubclass(filter_class, GeometryFilter):
            geom_type = params.get("geom_type", "GEOMETRY")
            if lookup_type == "contains":
                return "x,y | POINT(x y)"
            else:
                return f"GeoJSON | {geom_type}(x y ...)"
        elif issubclass(filter_class, filters.BaseInFilter):
            # Auto-generated "ConcreteInFilter" class, e.g. ModelIdChoiceFilterIn
            if issubclass(filter_class, filters.ModelChoiceFilter):
                return "id1,id2,...,idN"
            else:
                return "val,val,...,valN"

        try:
            return cls.LOOKUP_HELP_TEXT.get(lookup_type) or cls.FILTER_HELP_TEXT[filter_class]
        except KeyError:
            return filter_class.__name__.replace("Filter", "").lower()
