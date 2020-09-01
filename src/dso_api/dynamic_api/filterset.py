"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type
import logging
import re

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.gis.db.models.fields import (
    PolygonField,
    MultiPolygonField,
)
from django.http import Http404

from rest_framework_dso import filters as dso_filters
from schematools.contrib.django.models import DynamicModel
from schematools.utils import to_snake_case, toCamelCase

logger = logging.getLogger(__name__)


# These extra lookups are available for specific data types:
_comparison_lookups = ["exact", "gte", "gt", "lt", "lte", "not", "isnull"]
_identifier_lookups = [
    "exact",
    "in",
    "not",
    "isnull",
]  # needs ForeignObject.register_lookup()
_polygon_lookups = ["exact", "contains", "isnull", "not"]
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
            match = re.match(
                r"^(?P<key>[a-zA-Z0-9\_\.\-]+)(?P<lookup>[\[\]a-zA-Z0-9\.]+|)", value
            )
            if match is not None:
                return "".join([toCamelCase(match["key"]), match["lookup"]])
            return toCamelCase(value)

        # Apply camelCase to the filter names, after they've been initialized
        # using the model fields snake_case as input.
        return {
            filter_to_camel_case(attr_name): filter
            for attr_name, filter in filters.items()
        }


def _valid_rd(x, y):

    rd_x_min = 100000
    rd_y_min = 450000
    rd_x_max = 150000
    rd_y_max = 500000

    if not rd_x_min <= x <= rd_x_max:
        return False

    if not rd_y_min <= y <= rd_y_max:
        return False

    return True


def _valid_lat_lon(lat, lon):

    lat_min = 52.03560
    lat_max = 52.48769
    lon_min = 4.58565
    lon_max = 5.31360

    if not lat_min <= lat <= lat_max:
        return False

    if not lon_min <= lon <= lon_max:
        return False

    return True


def _convert_input_to_float(value):
    err = None

    lvalues = value.split(",")
    if len(lvalues) < 2:
        return None, None, None, f"Not enough values x, y {value}"

    x = lvalues[0]
    y = lvalues[1]
    radius = lvalues[2] if len(lvalues) > 2 else None

    # Converting to float
    try:
        x = float(x)
        y = float(y)
        radius = None if radius is None else int(radius)
    except ValueError:
        return None, None, None, f"Invalid value {x} {y} {radius}"

    # checking sane radius size
    if radius is not None and radius > 1000:
        return None, None, None, "radius too big"

    return x, y, radius, err


def _validate_x_y(value):
    """
    Check if we get valid values
    """
    point = None

    x, y, radius, err = _convert_input_to_float(value)

    if err:
        return None, None, err

    # Checking if the given coords are valid

    if _valid_rd(x, y):
        point = Point(x, y, srid=28992)
    elif _valid_lat_lon(x, y):
        point = Point(y, x, srid=4326).transform(28992, clone=True)
    else:
        err = "Coordinates received not within Amsterdam"

    return point, radius, err


def location_filter(queryset, _filter_name, value):
    """
    Filter based on the geolocation. This filter actually
    expect 2 or 3 numerical values: x, y and optional radius
    The value given is broken up by ',' and converted
    to the value tuple
    """

    point, radius, err = _validate_x_y(value)

    if err:
        logger.exception(err)
        # Creating one big queryset
        raise Http404("Invalid filter") from None

    # Creating one big queryset
    (geo_field, geo_type) = _filter_name.split(":")

    if geo_type.lower() == "polygon" and radius is None:
        args = {"__".join([geo_field, "contains"]): point}
        results = queryset.filter(**args)
    elif radius is not None:
        args = {"__".join([geo_field, "dwithin"]): (point, D(m=radius))}
        results = queryset.filter(**args).annotate(afstand=Distance(geo_field, point))
    else:
        err = "Radius in argument expected"
        logger.exception(err)
        raise Http404(err)
    return results


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
            fields[relation.name] = ["exact"]
            continue
        if not schema_fields[relation.name].is_nested_table:
            continue

        relation_properties = schema_fields[relation.name]["items"]["properties"]
        for field_name, field_schema in relation_properties.items():
            # contert space separated property name into snake_case name
            model_field_name = to_snake_case(field_name)
            model_field = getattr(relation.related_model, model_field_name).field
            filter_class = dso_filters.DSOFilterSet.FILTER_DEFAULTS.get(
                model_field.__class__
            )
            if filter_class is None:
                # No mapping found for this model field, skip it.
                continue
            filter_class = filter_class["filter_class"]

            # Filter name presented in API
            filter_name = "{}.{}".format(
                toCamelCase(relation.name), toCamelCase(field_name),
            )
            filter_lookups = _get_field_lookups(model_field)
            for lookup_expr in filter_lookups:
                # Generate set of filters per lookup (e.g. __lte, __gte etc)
                subfilter_name = filter_name
                if lookup_expr not in ["exact", "contains"]:
                    subfilter_name = f"{filter_name}[{lookup_expr}]"
                filters[subfilter_name] = filter_class(
                    field_name="__".join([relation.name, model_field_name]),
                    lookup_expr=lookup_expr,
                    label=dso_filters.DSOFilterSet.FILTER_HELP_TEXT.get(
                        filter_class, lookup_expr
                    ),
                )
                fields[subfilter_name] = filter_lookups

    return filters


def generate_additional_filters(model: Type[DynamicModel]):
    filters = {}
    for filter_name, options in model._table_schema.filters.items():
        try:
            filter_class = ADDITIONAL_FILTERS[options.get("type", "range")]
        except KeyError:
            logger.warning(f"Incorrect filter type: {options}")
        else:
            filters[filter_name] = filter_class(
                label=filter_class.label,
                start_field=options.get("start"),
                end_field=options.get("end"),
            )

    return filters


def _get_field_lookups(field: models.Field) -> list:
    """Find the possible lookups for a given field type."""
    return DEFAULT_LOOKUPS_BY_TYPE.get(field.__class__, ["exact"])
