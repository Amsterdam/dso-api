from __future__ import annotations

from django.utils.functional import LazyObject, empty
from rest_framework import serializers

DictOfDicts = dict[str, dict[str, dict]]


def unlazy_object(obj):
    if isinstance(obj, LazyObject):
        if obj._wrapped is empty:
            obj._setup()
        return obj._wrapped
    else:
        return obj


def group_dotted_names(dotted_field_names: list[str]) -> DictOfDicts:
    """Convert a list of dotted names to tree."""
    result = {}
    for dotted_name in dotted_field_names:
        tree_level = result
        for path_item in dotted_name.split("."):
            tree_level = tree_level.setdefault(path_item, {})
    return result


def get_serializer_relation_lookups(
    serializer: serializers.BaseSerializer, prefix=""
) -> dict[str, serializers.Field]:
    """Find all relations that a serializer instance would request.
    This allows to prepare a ``prefetch_related()`` call on the queryset.
    """
    from rest_framework_dso.serializers import HALRawIdentifierLinkSerializer

    # Unwrap the list serializer construct for the one-to-many relationships.
    if isinstance(serializer, serializers.ListSerializer):
        serializer = serializer.child

    lookups: dict[str, serializers.Field] = {}

    for field in serializer.fields.values():  # type: serializers.Field
        if isinstance(field, HALRawIdentifierLinkSerializer):
            # Shortcircuit serializer objects that only receive a string value (like a CharField).
            # This doesn't need to be passed to prefetch_related.
            continue
        elif field.source == "*":
            if isinstance(field, serializers.BaseSerializer):
                # When a serializer receives the same data as the parent instance, it can be
                # seen as being a part of the parent. The _links field is implemented this way.
                lookups.update(get_serializer_relation_lookups(field, prefix=prefix))
        elif isinstance(
            field,
            (
                serializers.BaseSerializer,  # also ListSerializer
                serializers.RelatedField,
                serializers.ManyRelatedField,
            ),
        ):
            # Note this could overwrite a value, as embedded fields could overlap with _links.
            lookup = f"{prefix}{'__'.join(field.source_attrs)}"
            lookups[lookup] = field

            if isinstance(field, serializers.BaseSerializer):
                lookups.update(get_serializer_relation_lookups(field, prefix=f"{lookup}__"))
    return lookups
