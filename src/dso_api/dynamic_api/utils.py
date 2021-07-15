import re
from functools import lru_cache
from typing import Tuple, Type

from django.db.models import Model
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from schematools.contrib.django.models import LooseRelationField
from schematools.contrib.django.signals import dynamic_models_removed

PK_SPLIT = re.compile("[_.]")


def split_on_separator(value):
    """Split on the last separator, which can be a dot or underscore."""
    # reversal is king
    return [part[::-1] for part in PK_SPLIT.split(value[::-1], 1)][::-1]


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: resolve_model_lookup.cache_clear())


@lru_cache()
def resolve_model_lookup(model: Type[Model], lookup: str) -> Tuple[Type[Model], bool]:
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
