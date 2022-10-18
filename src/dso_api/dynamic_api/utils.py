from __future__ import annotations

import re
from functools import lru_cache

from django.db import models
from django.db.models import Model
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from rest_framework import serializers
from schematools.contrib.django.models import DynamicModel
from schematools.contrib.django.signals import dynamic_models_removed
from schematools.naming import to_snake_case

from rest_framework_dso.fields import GeoJSONIdentifierField

PK_SPLIT = re.compile("[_.]")


def split_on_separator(value):
    """Split on the last separator, which can be a dot or underscore."""
    # reversal is king
    return [part[::-1] for part in PK_SPLIT.split(value[::-1], 1)][::-1]


def get_view_name(model: type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param model: The dynamic model.
    :param suffix: This can be "detail" or "list".
    """
    dataset_id = to_snake_case(model.get_dataset_id())
    table_id = to_snake_case(model.get_table_id())
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: resolve_model_lookup.cache_clear())


@lru_cache
def resolve_model_lookup(model: type[Model], lookup: str) -> list[RelatedField | ForeignObjectRel]:
    """Find which fields a lookup points to.
    :returns: The model fields that the relation traverses.
    """
    if not lookup:
        raise ValueError("Empty lookup can't be resolved")

    fields = []
    for field_name in lookup.split("__"):
        field = model._meta.get_field(field_name)

        if isinstance(field, (RelatedField, ForeignObjectRel)):
            # RelatedField covers all forwards relations (ForeignKey, ManyToMany, OneToOne)
            # ForeignObjectRel covers backward relations (ManyToOneRel, ManyToManyRel, OneToOneRel)
            model = field.related_model
        else:
            raise ValueError(f"Field '{field}' is not a relation in lookup '{lookup}'")

        fields.append(field)

    return fields


def get_serializer_source_fields(  # noqa: C901
    serializer: serializers.BaseSerializer, prefix=""
) -> list[str]:
    """Find which ORM fields a serializer instance would request.

    It checks "serializer.fields", and analyzes each "field.source" to find
    the model attributes that would be read.
    This allows to prepare an ``only()`` call on the queryset.
    """
    # Unwrap the list serializer construct for the one-to-many relationships.
    if isinstance(serializer, serializers.ListSerializer):
        serializer = serializer.child

    lookups = []

    for field in serializer.fields.values():  # type: serializers.Field
        if field.source == "*":
            # Field takes the full object, only some cases are supported:
            if isinstance(field, serializers.BaseSerializer):
                # When a serializer receives the same data as the parent instance, it can be
                # seen as being a part of the parent. The _links field is implemented this way.
                lookups.extend(get_serializer_source_fields(field, prefix=prefix))
            elif isinstance(field, serializers.HyperlinkedRelatedField):
                # Links to an object e.g. TemporalHyperlinkedRelatedField
                # When the lookup_field matches the identifier, there is no need
                # to add the field because the parent name is already includes it.
                if field.lookup_field != "pk":
                    lookups.append(f"{prefix}{field.lookup_field}")
            elif field.field_name == "schema" or isinstance(field, GeoJSONIdentifierField):
                # Fields that do have "source=*", but don't read any additional fields.
                # e.g. SerializerMethodField for schema, and GeoJSON ID field.
                continue
            elif isinstance(field, serializers.CharField):
                # A CharField(source="*") that either receives a str from its parent
                # (e.g. _loose_link_serializer_factory() receives a str as data),
                # or it's reading DynamicModel.__str__().
                if (
                    isinstance(serializer, serializers.ModelSerializer)
                    and (display_field := serializer.Meta.model.table_schema().display_field)
                    is not None
                ):
                    lookups.append(f"{prefix}{display_field.python_name}")
                continue
            else:
                raise NotImplementedError(
                    f"Can't determine .only() for {prefix}{field.field_name}"
                    f" ({field.__class__.__name__})"
                )
        else:
            # Check the field isn't a reverse field, this should not be mentioned at all
            # because such field doesn't access a local field (besides the primary key).
            model_fields = get_source_model_fields(serializer, field.field_name, field)
            if isinstance(model_fields[0], models.ForeignObjectRel):
                continue

            # Regular field: add the source value to the list.
            lookup = f"{prefix}{'__'.join(field.source_attrs)}"
            lookups.append(lookup)

            if isinstance(field, (serializers.ModelSerializer, serializers.ListSerializer)):
                lookups.extend(get_serializer_source_fields(field, prefix=f"{lookup}__"))

    # Deduplicate the final result, as embedded fields could overlap with _links.
    return sorted(set(lookups)) if not prefix else lookups


def get_source_model_fields(
    serializer: serializers.ModelSerializer, field_name: str, field: serializers.Field
) -> list[models.Field | models.ForeignObjectRel]:
    """Find the model fields that the serializer field points to.
    This is typically just one field, but `field.source` could be set to a dotted path.
    """
    model = serializer.Meta.model

    if field.source == "*":
        # These fields are special: they receive the entire model instead of an attribute value.
        if isinstance(field, serializers.HyperlinkedRelatedField):
            # While this field type receives the complete value (so it can access model._meta),
            # it only reads one attribute (the lookup_field). Need to translate "pk" through.
            source_attrs = [
                field.lookup_field if field.lookup_field != "pk" else model._meta.pk.name
            ]
        else:
            raise NotImplementedError(
                f"Unable to detect source for field.source == '*',"
                f" field: {field_name} ({field.__class__.__name__})"
            )
    elif hasattr(field, "source_attrs"):
        # Field.bind() was called, so `field.parent` and `field.source_attrs` are already set
        source_attrs = field.source_attrs
    else:
        # Early testing for the model field (e.g. in an override of get_fields()).
        source_attrs = (field.source or field_name).split(".")

    orm_path = []
    for attr in source_attrs:
        model_field = model._meta.get_field(attr)
        model = model_field.related_model  # for next loop.
        orm_path.append(model_field)

    return orm_path
