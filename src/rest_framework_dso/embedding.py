"""Logic to implement object embedding, and retrieval in a streaming-like fashion.

It's written in an observer/listener style, allowing the embedded data to be determined
during the rendering. Instead of having to load the main results in memory for analysis,
the main objects are inspected while they are consumed by the output stream.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from copy import copy
from dataclasses import dataclass
from functools import cached_property

from django.db import models
from django.db.models import ForeignObjectRel
from drf_spectacular.drainage import get_override
from rest_framework import serializers
from rest_framework.exceptions import ParseError

from rest_framework_dso.fields import AbstractEmbeddedField
from rest_framework_dso.iterators import ChunkedQuerySetIterator
from rest_framework_dso.serializer_helpers import ReturnGenerator
from rest_framework_dso.utils import (
    DictOfDicts,
    get_serializer_relation_lookups,
    group_dotted_names,
)

logger = logging.getLogger(__name__)

MAX_EXPAND_ALL_DEPTH = 2


class ExpandScope:
    """The parsed expand query parameter.

    There are 2 possible scenario's:

    * All fields should expand ("auto expand all"), e.g. a request with ``?_expand=true``.
    * A explicit list of field names to expand, allowing dotted notations for sub-expands.
      That includes requests with an ``?_expandScope=`` parameter.
    """

    def __init__(self, expand: str | None = None, expand_scope: list[str] | str | None = None):
        """Parse the (raw) request parameters"""
        self.auto_expand_all = False
        self._expand_scope = None
        self._nested_fields_to_expand = None

        if expand_scope and isinstance(expand_scope, str):
            expand_scope = expand_scope.split(",")

        # Initialize from request
        if expand == "true":
            # ?_expand=true should export all fields, unless `&_expandScope=..` is also given.
            if expand_scope:
                self._expand_scope = expand_scope
            else:
                self.auto_expand_all = True
        elif expand == "false":
            self._expand_scope = None
            self.auto_expand_all = False
        elif expand:
            raise ParseError(
                "Only _expand=true|false is allowed. Use _expandScope to expand specific fields."
            ) from None
        elif expand_scope:
            # Backwards compatibility, also allow `?_expandScope` without stating `?_expand=true`
            # otherwise, parse as a list of fields to expand.
            self._expand_scope = expand_scope

    def __bool__(self):
        """Whether fields need to be expanded."""
        return bool(self.auto_expand_all or self._expand_scope)

    def __repr__(self):
        return f"<ExpandScope: all={self.auto_expand_all}, scope={self._expand_scope!r}>"

    def _as_nested(self, nested_fields_to_expand):
        """Create a scope that starts from a sub-level"""
        scope = copy(self)
        scope._nested_fields_to_expand = nested_fields_to_expand
        return scope

    def get_expanded_fields(
        self,
        parent_serializer: serializers.Serializer,
        allow_m2m=True,
        prefix="",
    ) -> list[EmbeddedFieldMatch]:
        """Find the expanded fields in a serializer that are requested.
        This translates the ``_expand`` query into a dict of embedded fields.
        """
        if not self:
            return []

        if self._nested_fields_to_expand is not None:
            # Sub-level, overruled
            field_tree = self._nested_fields_to_expand
        elif self.auto_expand_all:
            # Top-level, need to find all fields
            # We auto-expand only for a limited set of levels, to avoid returning way too much
            field_tree = get_all_embedded_field_names(
                parent_serializer.__class__,
                allow_m2m=allow_m2m,
                max_depth=MAX_EXPAND_ALL_DEPTH,
            )
        else:
            # Top-level, find all field that were requested.
            field_tree = group_dotted_names(self._expand_scope)
            self._validate(parent_serializer.__class__, field_tree, allow_m2m, prefix=prefix)

        if not field_tree:
            return []

        embedded_fields = []

        for field_name, nested_fields_to_expand in field_tree.items():
            field = get_embedded_field(parent_serializer.__class__, field_name, prefix=prefix)

            # Some output formats don't support M2M, so avoid expanding these.
            if field.is_array and not allow_m2m:
                raise ParseError(
                    f"Eager loading is not supported for"
                    f" field '{prefix}{field_name}' in this output format"
                )

            embedded_fields.append(
                EmbeddedFieldMatch(
                    parent_serializer,
                    field_name,
                    field,
                    prefix,
                    nested_expand_scope=self._as_nested(nested_fields_to_expand),
                )
            )

        return embedded_fields

    def _validate(
        self,
        serializer_class: type[serializers.Serializer],
        field_tree: DictOfDicts,
        allow_m2m: bool,
        prefix: str = "",
    ):
        """Validate whether all selected fields exist."""

        for field_name, nested_fields_to_expand in field_tree.items():
            field = get_embedded_field(serializer_class, field_name, prefix=prefix)
            if nested_fields_to_expand:
                self._validate(field.serializer_class, nested_fields_to_expand, allow_m2m)


@dataclass
class EmbeddedFieldMatch:
    """Details of an embedded field,
    with the associated metadata to resolve additional nested embeds too.
    """

    #: The parent serializer where the expanded field exists
    serializer: serializers.Serializer

    #: Name of the expanded field
    name: str

    #: Expanded field definition (shared object between all serializer instances!)
    field: AbstractEmbeddedField

    #: Prefix when this is a nested field
    prefix: str

    #: Additional nested expands that were requested for this field.
    nested_expand_scope: ExpandScope

    def __repr__(self):
        # Avoid long serializer repr which makes output unreadable.
        return (
            f"<{self.__class__.__name__}:"
            f" {self.serializer.__class__.__name__}"
            f" field={self.field!r}"
            f" nested={self.nested_expand_scope!r}>"
        )

    @property
    def full_name(self) -> str:
        """Return the full dotted name of the field."""
        return f"{self.prefix}{self.name}"

    @cached_property
    def embedded_serializer(self) -> serializers.Serializer:
        """Provide the serializer for the embedded relation."""
        # The nested 'fields_to_expand' data is provided to the child serializer,
        # so it can expand the next nesting if needed.
        from .serializers import DSOSerializer, ExpandableSerializer

        kwargs = {}
        if issubclass(self.field.serializer_class, ExpandableSerializer):
            kwargs["fields_to_expand"] = self.nested_expand_scope
        elif self.nested_expand_scope:
            raise RuntimeError("EmbeddedField serializer does not support nesting embeds")

        if isinstance(self.serializer, DSOSerializer):
            # Also the 'fields_to_display' to the nested serializer
            nested_fields_to_display = self.serializer.fields_to_display.as_nested(self.name)
            if issubclass(self.field.serializer_class, DSOSerializer):
                kwargs["fields_to_display"] = nested_fields_to_display
            elif nested_fields_to_display:
                raise RuntimeError(
                    "EmbeddedField serializer does not support reducing return fields"
                )

        serializer = self.field.get_serializer(parent=self.serializer, **kwargs)

        # By reading serializer.fields early,
        # a check on fields_to_display also runs before rendering.
        child = (
            serializer.child if isinstance(serializer, serializers.ListSerializer) else serializer
        )
        child.fields  # noqa: B018, perform early checks

        # Allow the output format to customize the serializer for the embedded relation.
        renderer = self.serializer.context["request"].accepted_renderer
        if hasattr(renderer, "tune_serializer"):
            renderer.tune_serializer(serializer)

        return serializer


def get_all_embedded_field_names(
    serializer_class: type[serializers.Serializer],
    allow_m2m=True,
    max_depth: int = 99,
    source_fields: list[models.Field | ForeignObjectRel] | None = None,
) -> DictOfDicts:
    """Find all possible expands, including nested fields.
    The output format is identical to group_dotted_names().
    """
    result = {}
    embedded_fields: dict[str, AbstractEmbeddedField] = getattr(
        serializer_class.Meta, "embedded_fields", {}
    )

    for field_name, field in embedded_fields.items():
        if field.is_array and not allow_m2m:
            continue

        if source_fields and field.source_field.remote_field in source_fields:
            # Avoid embedding the exact reverse of a parent relation.
            logger.debug(
                "Excluded %s from embedding, it will recurse back on itself through %s.%s",
                field_name,
                ".".join(f.name for f in source_fields),
                field.source,
            )
            continue

        if max_depth >= 1:
            child_source_fields = (source_fields or []) + [field.source_field]
            # If there are nested relations, these are found too.
            # otherwise the value becomes an empty dict.
            result[field_name] = get_all_embedded_field_names(
                field.serializer_class,
                allow_m2m=allow_m2m,
                max_depth=max_depth - 1,
                source_fields=child_source_fields,
            )
        else:
            result[field_name] = {}

    return result


def get_all_embedded_fields_by_name(
    serializer_class: type[serializers.Serializer], allow_m2m=True, prefix="", maxdepth=4
) -> dict[str, AbstractEmbeddedField]:
    """Find all possible embedded fields, as lookup table with their dotted names."""
    result = {}

    deprecated = get_override(serializer_class, "deprecate_fields", default=[])

    for field_name in getattr(serializer_class.Meta, "embedded_fields", ()):
        field: AbstractEmbeddedField = get_embedded_field(serializer_class, field_name)
        if (
            (field.is_array and not allow_m2m)
            or field.field_name in deprecated  # avoid deprecated embeds (e.g. hftRelMtVot)
            # Avoid recursion (e.g. heeftHoofdadres.adresseertVerblijfsobject.heeftHoofdadres.)
            or f".{field_name}." in prefix
            or prefix.startswith(f"{field_name}.")
        ):
            continue

        lookup = f"{prefix}{field_name}"
        result[lookup] = field

        if maxdepth > 1:
            result.update(
                get_all_embedded_fields_by_name(
                    field.serializer_class,
                    allow_m2m=allow_m2m,
                    prefix=f"{lookup}.",
                    maxdepth=maxdepth - 1,
                )
            )

    return result


def get_embedded_field(
    serializer_class: type[serializers.Serializer], field_name: str, prefix: str = ""
) -> AbstractEmbeddedField:
    """Retrieve the embedded fields.
    This method can be called with any type of serializer,
    but only returns returns results for an ``ExpandableSerializer``.
    """
    try:
        # Delegate the actual logic to the serializer so it can be overwritten.
        _real_get_embedded_field = serializer_class.get_embedded_field
    except AttributeError:
        raise ParseError(
            f"Eager loading is not supported for field '{prefix}{field_name}'"
        ) from None
    else:
        return _real_get_embedded_field(field_name, prefix=prefix)


class EmbeddedResultSet(ReturnGenerator):
    """A wrapper for the returned expanded fields.
    This is used in combination with the ObservableIterator.

    This result set is lazily evaluated. It doesn't contain any results on creation.
    Instead, :meth:`inspect_instance` should be called first to find related objects.
    These will be retrieved efficiently once this object is iterated.

    The :func:`inspect_instance` is called each time an object is retrieved.
    As alternative, all instances *can* be provided at construction, which is
    typically useful for a detail page as this breaks streaming otherwise.
    """

    @classmethod
    def from_match(cls, match: EmbeddedFieldMatch):
        """Generate the resultset that will walk through all relations.
        The result set also implements the generator-like behavior
        that the rendering needs to preserve streaming.
        """
        return cls(match.field, serializer=match.embedded_serializer, full_name=match.full_name)

    def __init__(
        self,
        embedded_field: AbstractEmbeddedField,
        serializer: serializers.Serializer,
        main_instances: list | None = None,
        full_name: str | None = None,
    ):
        # Embedded result sets always work on child elements,
        # as the source queryset is iterated over within this class.
        if isinstance(serializer, serializers.ListSerializer):
            serializer = serializer.child

        super().__init__(generator=None, serializer=serializer)
        self.embedded_field = embedded_field
        self.id_list = []
        self.full_name = full_name

        # Allow to pre-feed with instances (e.g for detail view)
        if main_instances is not None:
            for instance in main_instances:
                self.inspect_instance(instance)

    def inspect_instance(self, instance, **kwargs):
        """Inspect a main object to find any references for this embedded result.
        (kwargs can be the observable_iterator)."""
        ids = self.embedded_field.get_related_ids(instance)
        if ids:
            self.id_list.extend(ids)

    def get_objects(self) -> Iterator[models.Model]:
        """Retrieve the objects to render."""
        queryset = self.serializer.get_embedded_objects_by_id(self.embedded_field, self.id_list)
        if not isinstance(queryset, models.QuerySet):
            return queryset  # may return an iterator, can't optimize

        return self.optimize_queryset(queryset)

    def optimize_queryset(self, queryset):
        """Optimize the queryset, see if N-query calls can be avoided for the embedded object."""
        lookups = get_serializer_relation_lookups(self.serializer)
        if lookups:
            # To make prefetch_related() work, the queryset needs to be read in chunks.
            return ChunkedQuerySetIterator(queryset.prefetch_related(*lookups))
        else:
            # Don't need to analyse intermediate results,
            # read the queryset in the most efficient way.
            return queryset.iterator()

    def __iter__(self):
        """Create the generator on demand when iteration starts.
        At this point, the ID's are known that need to be fetched.
        """
        if not self.id_list:
            return iter(())  # Avoid querying databases for empty sets.

        if self.generator is None:
            self.generator = self._build_generator()

        logger.debug(
            "Fetching embedded field: %s", self.full_name or self.embedded_field.field_name
        )
        return super().__iter__()  # returns iter(self.generator)

    def __bool__(self):
        if self.generator is None:
            self.generator = self._build_generator()
        return super().__bool__()

    def _build_generator(self):
        """Create the generator on-demand"""
        return (self.serializer.to_representation(instance) for instance in self.get_objects())
