"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type
import logging
import re

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db.models.fields import (
    PolygonField,
    MultiPolygonField,
)
from django_postgres_unlimited_varchar import UnlimitedCharField

from rest_framework_dso import filters as dso_filters
from schematools.contrib.django.models import DynamicModel
from schematools.utils import to_snake_case, toCamelCase

logger = logging.getLogger(__name__)


# These extra lookups are available for specific data types.
# The identifier lookups needs ForeignObject.register_lookup()
_comparison_lookups = ["exact", "gte", "gt", "lt", "lte", "not", "isnull"]
_identifier_lookups = ["exact", "in", "not", "isnull"]
_polygon_lookups = ["exact", "contains", "isnull", "not"]
_string_lookups = ["exact", "isnull", "not", "isempty", "like"]
DEFAULT_LOOKUPS_BY_TYPE = {
    models.AutoField: _identifier_lookups,
    models.TextField: _string_lookups,
    models.CharField: _string_lookups,
    UnlimitedCharField: _string_lookups,
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
    PolygonField: _polygon_lookups,
    MultiPolygonField: _polygon_lookups,
}

ADDITIONAL_FILTERS = {
    "range": dso_filters.RangeFilter,
}


class DynamicFilterSet(dso_filters.DSOFilterSet):
    """Base class for dynamic filter sets."""

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()

        def filter_to_camel_case(value):
            """
            Convert filters to camelCase, not including [lookups].
            """
            match = re.match(r"^(?P<key>[a-zA-Z0-9\_\.\-]+)(?P<lookup>[\[\]a-zA-Z0-9\.]+|)", value)
            if match is not None:
                return "".join([toCamelCase(match["key"]), match["lookup"]])
            return toCamelCase(value)

        # Apply camelCase to the filter names, after they've been initialized
        # using the model fields snake_case as input.
        return {filter_to_camel_case(attr_name): filter for attr_name, filter in filters.items()}


def filterset_factory(model: Type[DynamicModel]) -> Type[DynamicFilterSet]:
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.
    fields = {
        f.attname: _get_field_lookups(f)
        for f in model._meta.get_fields()
        if isinstance(f, (models.fields.Field, models.fields.related.ForeignKey))
    }

    filters = generate_relation_filters(model)
    filters.update(generate_additional_filters(model))

    # Generate the class
    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta, **filters})


def generate_relation_filters(model: Type[DynamicModel]):  # NoQA
    """
    Generates additional filters for relations, including sub items.
    """
    fields = dict()
    filters = dict()

    for relation in model._meta.related_objects:
        schema_fields = dict([(f.name, f) for f in model._table_schema.fields])
        if relation.name not in schema_fields:
            fields[relation.name] = ["exact"]
            continue
        if not schema_fields[relation.name].is_nested_table:
            continue

        relation_properties = schema_fields[relation.name]["items"]["properties"]
        for field_name, field_schema in relation_properties.items():
            # contert space separated property name into snake_case name
            model_field_name = to_snake_case(field_name)
            model_field = getattr(relation.related_model, model_field_name).field
            filter_class = dso_filters.DSOFilterSet.FILTER_DEFAULTS.get(model_field.__class__)
            if filter_class is None:
                # No mapping found for this model field, skip it.
                continue
            filter_class = filter_class["filter_class"]

            # Filter name presented in API
            filter_name = "{}.{}".format(
                toCamelCase(relation.name),
                toCamelCase(field_name),
            )
            filter_lookups = _get_field_lookups(model_field)
            for lookup_expr in filter_lookups:
                # Generate set of filters per lookup (e.g. __lte, __gte etc)
                subfilter_name = filter_name
                if lookup_expr not in ["exact", "contains"]:
                    subfilter_name = f"{filter_name}[{lookup_expr}]"

                filter_instance = filter_class(
                    field_name="__".join([relation.name, model_field_name]),
                    lookup_expr=lookup_expr,
                    label=dso_filters.DSOFilterSet.FILTER_HELP_TEXT.get(filter_class, lookup_expr),
                )

                if lookup_expr == "not":
                    # Allow multiple NOT filters
                    filter_instance = dso_filters.MultipleValueFilter(filter_instance)

                filters[subfilter_name] = filter_instance
                fields[subfilter_name] = filter_lookups

    return filters


def generate_additional_filters(model: Type[DynamicModel]):
    filters = {}
    for filter_name, options in model._table_schema.filters.items():
        try:
            filter_class = ADDITIONAL_FILTERS[options.get("type", "range")]
        except KeyError:
            logger.warning(f"Incorrect filter type: {options}")
            continue

        filters[filter_name] = filter_class(
            start_field=options.get("start"),
            end_field=options.get("end"),
            label=filter_class.label,
        )

    return filters


def _get_field_lookups(field: models.Field) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field.__class__, ["exact"])
