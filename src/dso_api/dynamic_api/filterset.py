"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type
from string_utils import slugify

from django.db import models
from django import forms
from django.contrib.gis.db.models import GeometryField
from django.contrib.postgres.fields import JSONField
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
        breakpoint()
        self.field_name = field_name
        lookup = [{inner_field: lookup}]
        return super().filter(qs, lookup)


class DynamicFilterSet(DSOFilterSet):
    """Base class for dynamic filter sets."""

    @classmethod
    def schema_fields(cls):
        if cls._meta.model is not None:
            return cls._meta.model._table_schema['schema']['properties']
        return []

    @classmethod
    def get_fields(cls):
        """
        Extends list of field lookups for Array fields with inner lookups.
        """
        fields = super().get_fields()
        for prop_name, prop in cls.schema_fields().items():
            if prop.get('type') != "array":
                continue
            lookups = []
            for field, spec in prop['entity']['properties'].items():
                slug = snake_to_camel_case(slugify(field, sign="_"))
                if spec.get("type") in ["time", "number"]:
                    lookups.append(f"{slug}__gt")
                    lookups.append(f"{slug}__gte")
                    lookups.append(f"{slug}__lt")
                    lookups.append(f"{slug}__lte")
                elif spec.get("type") in ["string", "array"]:
                    lookups.append(f"{slug}__exact")
            fields[prop_name] = lookups
        return fields

    @classmethod
    def filter_for_field(cls, field, field_name, lookup_expr='exact'):
        """
        Mapping array specific inner lookups to proper filters.
        """
        filter_instance = super().filter_for_field(field, field_name, lookup_expr)
        prop = cls.schema_fields()[field_name]
        if prop.get('type') == "array":
            # slug = snake_to_camel_case(slugify(field, sign="_"))
            if lookup_expr.endswith('__exact'):
                filter_class, params = cls.filter_for_lookup(field, lookup_type='exact')
                inner_field = lookup_expr.replace("__exact", "")
                params.update(dict(
                    lookup_expr="contains",
                    field_name=f"{field_name}__{inner_field}"
                ))
                print(filter_class, params)
                filter_instance = DynamicArrayFilter(
                    meta_properties=prop,
                    **params
                )
            print("whooo", lookup_expr, filter_instance)
        return filter_instance

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
    fields = {f.attname: _get_field_lookups(f) for f in model._meta.get_fields()}

    # filters = dict()
    # for prop_name, prop in model._table_schema['schema']['properties'].items():
    #     if prop.get('type') != "array":
    #         continue
    #     for field, spec in prop['entity']['properties'].items():
    #         field_slug = snake_to_camel_case(slugify(field, sign="_"))
    #         field_name = "__".join([prop_name, field_slug])
    #         if spec.get("type") == "time":
    #             filters[f"{field_name}__gt"] = dj_filters.CharFilter(
    #                 lookup_expr="gt", help_text=spec.get("type")
    #             )# dj_filters.TimeFilter(field_name=field_name, help_text=spec.get("type"))
    #             filters[f"{field_name}__lt"] = dj_filters.CharFilter(
    #                 field_name=field_name,
    #                 lookup_expr="lt",
    #                 help_text=spec.get("type")
    #             )# dj_filters.TimeFilter(field_name=field_name, help_text=spec.get("type"))
    #         if spec.get("type") == "array":
    #             filters[field_name] = dj_filters.CharFilter(
    #                 lookup_expr='%s__exact' % field_slug,
    #                 help_text=spec.get("type"))# ChoiceField(choices=[('ma', 'ma'), ('zo', 'zo')], help_text=spec.get("type"))
    #         else:
    #             filters[field_name] = dj_filters.CharFilter(
    #                 field_name=field_name, # prop_name,
    #                 help_text=spec.get("type"),)
    #                 #lookup_expr='%s__icontains' % field_slug)


    # fields = dict()
    # for field in model._meta.get_fields():
    #     if field.primary_key or isinstance(field, GeometryField):
    #         # Do not filter on primary keys and geometry
    #         continue
    #     fields[field.name] = ['exact']
    #     schema_property = get_schema_property(model, field)
    #     if schema_property.get("type") == "array":
    #         # Remap array into set of filters
    #         for item, spec in schema_property["entity"]["properties"].items():
    #             item_name = snake_to_camel_case(slugify(item, sign="_"))
    #             if spec.get("type") == "time":
    # 
    #             print(item_name)

    # Generate the class
    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta})


def _get_field_lookups(field: models.Field) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field.__class__, ["exact"])


def get_schema_property(model, field):
    return model._table_schema["schema"]["properties"][field.name]
