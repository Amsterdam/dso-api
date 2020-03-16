"""
Creating filters for the dynamic model fields.
This uses the django-filter logic to process the GET parameters.
"""
from typing import Type

from django.contrib.gis.db.models import GeometryField

from dso_api.dynamic_api.utils import snake_to_camel_case
from dso_api.lib.schematools.models import DynamicModel
from rest_framework_dso.filters import DSOFilterSet


class DynamicFilterSet(DSOFilterSet):
    """Base class for dynamic filter sets."""

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()

        # Apply camelCase to the filter names, after they've been initialized
        # using the model fields snake_case as input.
        return {
            snake_to_camel_case(attr_name): filter
            for attr_name, filter in filters.items()
        }


def filterset_factory(model: Type[DynamicModel]) -> Type[DynamicFilterSet]:
    """Generate the filterset based on the dynamic model."""
    # See https://django-filter.readthedocs.io/en/master/guide/usage.html on how filters are used.
    # Determine which fields are included:
    # Excluding geometry fields for now, as the default filter only performs exact matches.
    # This isn't useful for polygon fields, and excluding it avoids support issues later.
    fields = [
        f.name
        for f in model._meta.get_fields()
        if not f.primary_key and not isinstance(f, GeometryField)
    ]

    # Generate the class
    meta_attrs = {
        "model": model,
        "fields": fields,
    }
    meta = type("Meta", (), meta_attrs)
    return type(f"{model.__name__}FilterSet", (DynamicFilterSet,), {"Meta": meta})
