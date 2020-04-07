"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django_filters import filters as dj_filters
from string_utils import slugify

from amsterdam_schema.types import field_is_nested_table
from dso_api.dynamic_api.utils import snake_to_camel_case, format_field_name
from dso_api.dynamic_api.serializers import DynamicSerializer
from dso_api.lib.schematools.models import DynamicModel, JSON_TYPE_TO_DJANGO
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


class DynamicFilter(dj_filters.CharFilter):
    def __init__(self, field_schema, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_schema = field_schema


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


def filterset_factory(model: Type[DynamicModel], serializer_class: Type[DynamicSerializer]) -> Type[DynamicFilterSet]:
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.
    fields = {f.attname: _get_field_lookups(f.__class__) for f in model._meta.get_fields()}

    filters = {}
    camel_case_fields = list(map(snake_to_camel_case, fields))
    for field_name in serializer_class.Meta.fields:
        if field_name not in ["_links", "schema"] + camel_case_fields:
            try:
                field_schema = model._table_schema['schema']['properties'][field_name]
            except KeyError:
                pass
            else:
                if field_is_nested_table(field_schema):
                    for inner_name, inner_field in field_schema['items']['properties'].items():
                        model_field = JSON_TYPE_TO_DJANGO[inner_field['type']][0]
                        filter_class = DSOFilterSet.FILTER_DEFAULTS.get(model_field)
                        if filter_class is not None:
                            filter_class = filter_class["filter_class"]
                            filter_name = "__".join([field_name, format_field_name(inner_name)])
                            field_lookups = _get_field_lookups(model_field)
                            for lookup_expr in field_lookups:
                                subfilter_name = filter_name
                                if lookup_expr != 'exact':
                                    subfilter_name = f"{filter_name}__{lookup_expr}"
                                filters[subfilter_name] = filter_class(
                                    field_name="__".join([field_name, slugify(inner_name, sign='_')]),
                                    lookup_expr=lookup_expr if lookup_expr != 'exact' else 'contains',
                                    label=DSOFilterSet.FILTER_HELP_TEXT.get(filter_class, lookup_expr)
                                )
                                fields[subfilter_name] = field_lookups

    meta_attrs = {
        "model": model,
        "fields": fields,
        "serializer_class": serializer_class,
    }
    meta = type("Meta", (), meta_attrs)
    return type(
        f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta, **filters}
    )


def _get_field_lookups(field_class) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field_class, ["exact"])
