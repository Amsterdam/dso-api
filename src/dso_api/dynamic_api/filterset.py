"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type

from django.db import models
from django.contrib.postgres.fields import ArrayField

from amsterdam_schema.types import field_is_nested_table
from dso_api.dynamic_api.utils import snake_to_camel_case, format_api_field_name, format_field_name
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
    ArrayField: ["contains"],
}


class DynamicFilterSet(DSOFilterSet):
    """Base class for dynamic filter sets."""

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()

        # Apply camelCase to the filter names, after they've been initialized
        # using the model fields snake_case as input.
        return {
            snake_to_camel_case(attr_name): filter_class
            for attr_name, filter_class in filters.items()
        }


def filterset_factory(model: Type[DynamicModel]) -> Type[DynamicFilterSet]:
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.
    fields = {
        f.attname: _get_field_lookups(f.__class__) for f in model._meta.get_fields()
        if isinstance(f, models.fields.Field)
    }

    extra_fields, filters = generate_relation_filters(model)

    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(
        f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta, **filters}
    )


def generate_relation_filters(model: Type[DynamicModel]):
    """
    Generates additional filters for relations, including sub items.
    """
    fields = dict()
    filters = dict()

    for relation in model._meta.related_objects:
        schema_fields = dict([(f.name, f) for f in model._table_schema.fields])
        if relation.name not in schema_fields:
            continue
        if not field_is_nested_table(schema_fields[relation.name]):
            continue

        for field_name, field_schema in schema_fields[relation.name]['items']['properties'].items():
            # contert space separated property name into snake_case name
            model_field_name = format_field_name(field_name)
            model_field = getattr(relation.related_model, model_field_name).field
            filter_class = DSOFilterSet.FILTER_DEFAULTS.get(model_field.__class__)
            if filter_class is None:
                # No mapping found for this model field, skip it.
                continue
            filter_class = filter_class["filter_class"]
            # Filter name presented in API
            filter_name = "__".join([format_api_field_name(relation.name), format_api_field_name(field_name)])
            filter_lookups = _get_field_lookups(model_field)
            for lookup_expr in filter_lookups:
                # Generate set of filters per lookup (e.g. __lte, __gte etc)
                subfilter_name = filter_name
                if lookup_expr not in ['exact', 'contains']:
                    subfilter_name = f"{filter_name}__{lookup_expr}"
                filters[subfilter_name] = filter_class(
                    field_name="__".join([relation.name, model_field_name]),
                    lookup_expr=lookup_expr,
                    label=DSOFilterSet.FILTER_HELP_TEXT.get(filter_class, lookup_expr)
                )
                fields[subfilter_name] = filter_lookups

    return fields, filters


def _get_field_lookups(field: models.Field) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field.__class__, ["exact"])
