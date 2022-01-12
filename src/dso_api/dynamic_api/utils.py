import re
from functools import lru_cache

from django.db import models
from django.db.models import Model
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from rest_framework import serializers
from schematools.contrib.django.models import LooseRelationField
from schematools.contrib.django.signals import dynamic_models_removed

PK_SPLIT = re.compile("[_.]")


def split_on_separator(value):
    """Split on the last separator, which can be a dot or underscore."""
    # reversal is king
    return [part[::-1] for part in PK_SPLIT.split(value[::-1], 1)][::-1]


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: resolve_model_lookup.cache_clear())


@lru_cache
def resolve_model_lookup(model: type[Model], lookup: str) -> tuple[type[Model], bool]:
    """Find which model a lookup points to.

    :returns: The model that the relation points to,
        and whether reading the relation could return multiple objects.
    """
    if not lookup:
        raise ValueError("Empty lookup can't be resolved")

    field = None
    for field_name in lookup.split("__"):
        field = model._meta.get_field(field_name)

        if isinstance(field, (RelatedField, ForeignObjectRel, LooseRelationField)):
            # RelatedField covers all forwards relations (ForeignKey, ManyToMany, OneToOne)
            # ForeignObjectRel covers backward relations (ManyToOneRel, ManyToManyRel, OneToOneRel)
            model = field.related_model
        else:
            raise ValueError(f"Field '{field}' is not a relation in lookup '{lookup}'")

    # As the x_to_y flags are set on all field types, they also work for the LooseRelationField,
    # which is neither of these (it's technically a 'many_to_one' like ForeignKey).
    return model, (field.many_to_many or field.one_to_many)


def get_source_model_fields(
    serializer: serializers.ModelSerializer, field_name: str, field: serializers.Field
) -> list[models.Field]:
    """Find the model fields that the serializer field points to.
    Typically this is only one field, but `field.source` could be set to a dotted path.
    """
    if field.source == "*":
        # These fields are special: they receive the entire model instead of a attribute value.
        raise ValueError("Unable to detect source for field.source == '*'")

    orm_path = []

    # Typically, `field.parent` and `field.source_attrs` are already set, making those arguments
    # unnecessary. However, most use-cases of this function involve inspecting model data earlier
    # in an override of serializer.get_fields(), which is before field.bind() is called.
    model = serializer.Meta.model
    source_attrs = getattr(field, "source_attrs", None) or (field.source or field_name).split(".")

    for attr in source_attrs:
        model_field = model._meta.get_field(attr)
        model = model_field.related_model
        orm_path.append(model_field)

    return orm_path
