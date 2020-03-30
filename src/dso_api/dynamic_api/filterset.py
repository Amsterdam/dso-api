"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type

from django.db import models
from django import forms
from django.contrib.gis.db.models import GeometryField
from django_filters import filters as dj_filters

from dso_api.dynamic_api.utils import snake_to_camel_case
from dso_api.lib.schematools.models import DynamicModel
from rest_framework_dso.filters import DSOFilterSet


# These extra lookups are available for specific data types:
_comparison_lookups = ["exact", "gte", "gt", "lt", "lte"]
_identifier_lookups = ["exact", "in"]
DEFAULT_LOOKUPS_BY_TYPE = {
    models.AutoField: _identifier_lookups,
    models.IntegerField: _comparison_lookups + ["in"],
    models.FloatField: _comparison_lookups + ["in"],
    models.DecimalField: _comparison_lookups + ["in"],
    models.DateField: _comparison_lookups,
    models.DateTimeField: _comparison_lookups,
    models.TimeField: _comparison_lookups,
    models.ForeignKey: _identifier_lookups,
    models.OneToOneField: _identifier_lookups,
    models.OneToOneRel: _identifier_lookups,
}


class DynamicArrayFilter(dj_filters.Filter):
    def __init__(self, meta_properties, *args, **kwargs):
        self._meta_properties = meta_properties
        super().__init__(*args, **kwargs)

    def filter(self, qs, lookup):
        if lookup is None:
            return qs
        field_name, inner_field = self.field_name.split("__")
        self.field_name = field_name
        lookup = [{inner_field: lookup}]
        return super().filter(qs, lookup)


class DynamicFilterSet(DSOFilterSet):
    """Base class for dynamic filter sets."""

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()

        # Apply camelCase to the filter names, after they've been initialized
        # using the model fields snake_case as input.
        base_filters = {
            snake_to_camel_case(attr_name): filter_class
            for attr_name, filter_class in filters.items()
        }

        return base_filters

    def filter_queryset(self, queryset):
        for name, value in self.form.cleaned_data.items():
            print(name, value)

        return super().filter_queryset(queryset)


def filterset_factory(model: Type[DynamicModel]) -> Type[DynamicFilterSet]:
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.
    fields = {
        f.attname: _get_lookups(f.__class__)
        for f in model._meta.get_fields()
        if not f.primary_key and not isinstance(f, GeometryField)
    }
    filters = {}
    # Extend fields with sub serializers
    for field_name, field in model._table_schema["schema"]["properties"].items():
        if field.get("type") == "array":
            fields[field_name] = ["exact"]
            filters[field_name] = dj_filters.CharFilter(
                lookup_expr='kenteken__exact',
                help_text=field["type"])

    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta, **filters})


def _get_field_lookups(field: models.Field) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field.__class__, ["exact"])


def get_schema_property(model, field):
    return model._table_schema["schema"]["properties"][field.name]


def _get_lookups(field_cls) -> list:
    return ['exact']
