"""
Dynamically generated filters for dynamic model fields.

The generic DSO logic is provided by :mod:`rest_framework_dso.filters`.
Both files build on top of the core logic from *django-filter*.
This file provides the translation and required bits for dynamic models.
"""
import logging
import re

from django.contrib.gis.db.models.fields import MultiPolygonField, PolygonField
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import ForeignKey
from django_postgres_unlimited_varchar import UnlimitedCharField
from schematools.contrib.django.models import DynamicModel, get_field_schema
from schematools.utils import to_snake_case, toCamelCase

from rest_framework_dso import filters as dso_filters

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
    models.BigIntegerField: _comparison_lookups + ["in"],
    models.FloatField: _comparison_lookups + ["in"],
    models.DecimalField: _comparison_lookups + ["in"],
    models.DateField: _comparison_lookups,
    models.DateTimeField: _comparison_lookups,
    models.TimeField: _comparison_lookups,
    models.ForeignKey: _identifier_lookups,
    models.OneToOneField: _identifier_lookups,
    models.OneToOneRel: _identifier_lookups,
    models.URLField: _string_lookups,
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


def filterset_factory(model: type[DynamicModel]) -> type[DynamicFilterSet]:  # noqa: C901
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.

    filters = {}  # declared filters
    fields = {}  # generated filters

    # Generate the generated filters (and declared filters for FK sunfields)
    for f in model._meta.get_fields():
        if isinstance(f, models.fields.Field):
            fields[f.attname] = _get_field_lookups(f)
        if isinstance(f, ForeignKey):
            fields[f.attname] = _get_field_lookups(f)  # backwards compat

            # In case of a composite FK, get the loose relations
            # associated with this ForeignKey object and add dotted syntax.
            schema_field = get_field_schema(f)
            prefix = f.attname.removesuffix("_id")

            try:
                subfields = schema_field.sub_fields
            except ValueError as e:
                # Check for the specific ValueError that signals no subfields.
                if "subfields are only possible" in str(e).lower():
                    continue
                raise

            for s in subfields:
                related_field_name = to_snake_case(s.id)
                model_field_name = f"{prefix}_{related_field_name}"
                try:
                    model_field = model._meta.get_field(model_field_name)
                except FieldDoesNotExist:
                    # the field is not part of the compound identifier
                    # we only support filtering on identifiers for now
                    continue

                filter_class = dso_filters.DSOFilterSet.FILTER_DEFAULTS[model_field.__class__][
                    "filter_class"
                ]

                for lookup in _get_field_lookups(model_field):
                    sub_filter_name = f"{prefix}.{related_field_name}"
                    if lookup not in ("contains", "exact"):
                        sub_filter_name = f"{sub_filter_name}[{lookup}]"

                    filters[sub_filter_name] = filter_class(
                        field_name=model_field_name,
                        lookup_expr=lookup,
                        label=dso_filters.DSOFilterSet.FILTER_HELP_TEXT.get(filter_class, lookup),
                    )

    # Generate the declared filters
    filters.update(_generate_relation_filters(model))
    filters.update(_generate_additional_filters(model))

    # Generate the class
    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta, **filters})


def _generate_relation_filters(model: type[DynamicModel]):  # noqa: C901
    """
    Generates additional filters for relations, including sub items.
    """
    filters = dict()

    schema_fields = {f.name: f for f in model._table_schema.fields}
    for relation in model._meta.related_objects:
        if relation.name not in schema_fields:
            continue
        if not schema_fields[relation.name].is_nested_table:
            continue

        relation_properties = schema_fields[relation.name]["items"]["properties"]
        for field_name, field_schema in relation_properties.items():
            # getattr() retrieved a DeferredAttribute here, hence the .field.
            model_field_name = to_snake_case(field_name)
            try:
                model_field = getattr(relation.related_model, model_field_name).field
            except AttributeError as e:
                raise AttributeError(
                    f"Unable to initialize dataset {model.get_dataset_id()}: {e}"
                ) from e

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
                if lookup_expr not in ("exact", "contains"):
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

    return filters


def _generate_additional_filters(model: type[DynamicModel]):
    filters = {}
    for filter_name, options in model._table_schema.additional_filters.items():
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
