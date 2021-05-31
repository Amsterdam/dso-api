"""Logic to implement object embedding, and retrieval in a streaming-like fashion.

It's written in an observer/listener style, allowing the embedded data to be determined
during the rendering. Instead of having to load the main results in memory for analysis,
the main objects are inspected while they are consumed by the output stream.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from itertools import islice
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Type, TypeVar, Union

from django.db import models
from lru import LRU
from rest_framework import serializers
from rest_framework.exceptions import ParseError

from rest_framework_dso.fields import AbstractEmbeddedField
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable

DictOfDicts = Dict[str, Dict[str, dict]]
T = TypeVar("T")
M = TypeVar("M", bound=models.Model)
DEFAULT_SQL_CHUNK_SIZE = 2000  # allow unit tests to alter this.


def parse_expand_scope(
    expand: Optional[str], expand_scope: Optional[str]
) -> Union[bool, List[str]]:
    """Parse the raw request parameters"""

    # Initialize from request
    if expand == "true":
        # ?_expand=true should export all fields, unless `&_expandScope=..` is also given.
        return expand_scope.split(",") if expand_scope else True
    elif expand == "false":
        return False
    elif expand:
        raise ParseError(
            "Only _expand=true|false is allowed. Use _expandScope to expand specific fields."
        ) from None

    # Backwards compatibility, also allow `?_expandScope` without stating `?_expand=true`
    # otherwise, parse as a list of fields to expand.
    return expand_scope.split(",") if expand_scope else False


def get_nested_fields_to_expand(
    serializer_class: Type[serializers.Serializer],
    expand_scope: Union[bool, List[str]],
    allow_m2m=True,
) -> DictOfDicts:
    """Convert the string value of ?_expand/_expandScope to a browsable tree."""
    if not expand_scope:
        return {}
    elif expand_scope is True:
        return get_all_embedded_field_names(serializer_class, allow_m2m=allow_m2m)
    else:
        return group_dotted_names(expand_scope)


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
    nested_fields_to_expand: DictOfDicts

    def __repr__(self):
        # Avoid long serializer repr which makes output unreadable.
        return (
            f"<{self.__class__.__name__}:"
            f" {self.field!r}"
            f" nested={self.nested_fields_to_expand!r}>"
        )

    @property
    def full_name(self) -> str:
        """Return the full dotted name of the field."""
        return f"{self.prefix}{self.name}"

    @cached_property
    def embedded_serializer(self):
        """Provide the serializer for the embedded relation."""
        # The nested 'fields_to_expand' data is provided to the child serializer,
        # so it can expand the next nesting if needed.
        from .serializers import ExpandMixin

        kwargs = {}
        if issubclass(self.field.serializer_class, ExpandMixin):
            kwargs["fields_to_expand"] = list(self.nested_fields_to_expand.keys())

        serializer = self.field.get_serializer(parent=self.serializer, **kwargs)

        # Allow the output format to customize the serializer for the embedded relation.
        renderer = self.serializer.context["request"].accepted_renderer
        if hasattr(renderer, "tune_serializer"):
            renderer.tune_serializer(serializer)

        return serializer


def get_expanded_fields_by_scope(
    parent_serializer: serializers.Serializer,
    expand_scope: Union[bool, List[str]],
    allow_m2m=True,
) -> List[EmbeddedFieldMatch]:
    """Find the expanded fields in a serializer that are requested.
    This translates the ``_expand`` query into a dict of embedded fields.
    """
    if not expand_scope:
        return []

    fields_to_expand = get_nested_fields_to_expand(
        parent_serializer.__class__, expand_scope, allow_m2m=allow_m2m
    )

    return get_expanded_fields(
        parent_serializer, fields_to_expand=fields_to_expand, allow_m2m=allow_m2m
    )


def get_expanded_fields(
    serializer: serializers.Serializer,
    fields_to_expand: DictOfDicts,
    allow_m2m=True,
    prefix="",
) -> List[EmbeddedFieldMatch]:
    """Find the expanded fields for a serializer object."""
    if not fields_to_expand:
        return []

    embedded_fields = []

    for field_name, nested_fields_to_expand in fields_to_expand.items():
        field = get_embedded_field(serializer.__class__, field_name, prefix)

        # Some output formats don't support M2M, so avoid expanding these.
        if field.is_array and not allow_m2m:
            raise ParseError(
                f"Eager loading is not supported for"
                f" field '{prefix}{field_name}' in this output format"
            )

        embedded_fields.append(
            EmbeddedFieldMatch(serializer, field_name, field, prefix, nested_fields_to_expand)
        )

    return embedded_fields


def get_all_embedded_field_names(
    serializer_class: Type[serializers.Serializer], allow_m2m=True
) -> DictOfDicts:
    """Find all possible expands, including nested fields.
    The output format is identical to group_dotted_names().
    """
    result = {}

    for field_name in getattr(serializer_class.Meta, "embedded_fields", ()):
        field: AbstractEmbeddedField = get_embedded_field(serializer_class, field_name)
        if field.is_array and not allow_m2m:
            continue

        # If there are nested relations, these are found too.
        # otherwise the value becomes an empty dict.
        result[field_name] = get_all_embedded_field_names(
            field.serializer_class, allow_m2m=allow_m2m
        )

    return result


def get_all_embedded_fields_by_name(
    serializer_class: Type[serializers.Serializer], allow_m2m=True, prefix=""
) -> Dict[str, AbstractEmbeddedField]:
    """Find all possible embedded fields, as lookup table with their dotted names."""
    result = {}

    for field_name in getattr(serializer_class.Meta, "embedded_fields", ()):
        field: AbstractEmbeddedField = get_embedded_field(serializer_class, field_name)
        if field.is_array and not allow_m2m:
            continue

        lookup = f"{prefix}{field_name}"
        result[lookup] = field
        result.update(
            get_all_embedded_fields_by_name(
                field.serializer_class, allow_m2m=allow_m2m, prefix=f"{lookup}."
            )
        )

    return result


def group_dotted_names(fields_to_expand: List[str]) -> DictOfDicts:
    """Convert a list of dotted names to tree."""
    result = {}
    for dotted_name in fields_to_expand:
        tree_level = result
        for path_item in dotted_name.split("."):
            tree_level = tree_level.setdefault(path_item, {})
    return result


def get_embedded_field(
    serializer_class: Type[serializers.Serializer], field_name, prefix=""
) -> AbstractEmbeddedField:
    """Retrieve an embedded field from the serializer class."""
    allowed_names = getattr(serializer_class.Meta, "embedded_fields", [])
    if field_name not in allowed_names:
        raise _expand_parse_error(allowed_names, field_name, prefix) from None

    try:
        return getattr(serializer_class, field_name)
    except AttributeError:
        raise RuntimeError(
            f"{serializer_class.__name__}.{field_name}" f" does not refer to an embedded field."
        ) from None


def _expand_parse_error(allowed_names, field_name, prefix=""):
    """Generate the proper exception for the invalid expand name"""
    available = ", {prefix}".format(prefix=prefix).join(sorted(allowed_names))
    if not available:
        return ParseError("Eager loading is not supported for this endpoint")
    else:
        return ParseError(
            f"Eager loading is not supported for field '{prefix}{field_name}', "
            f"available options are: {prefix}{available}"
        )


def get_serializer_lookups(serializer: serializers.BaseSerializer, prefix="") -> List[str]:
    """Find all relations that a serializer instance would request.
    This allows to prepare a ``prefetch_related()`` call on the queryset.
    """
    # Unwrap the list serializer construct for the one-to-many relationships.
    if isinstance(serializer, serializers.ListSerializer):
        serializer = serializer.child

    lookups = []
    for field in serializer.fields.values():
        if field.source == "*":
            if isinstance(field, serializers.BaseSerializer):
                # When a serializer receives the same data as the parent instance, it can be
                # seen as being a part of the parent. The _links field is implemented this way.
                lookups.extend(get_serializer_lookups(field, prefix=prefix))
        elif isinstance(
            field,
            (
                serializers.BaseSerializer,  # also ListSerializer
                serializers.RelatedField,
                serializers.ManyRelatedField,
            ),
        ):
            lookup = f"{prefix}{field.source.replace('.', '__')}"
            lookups.append(lookup)

            if isinstance(field, serializers.BaseSerializer):
                lookups.extend(get_serializer_lookups(field, prefix=f"{lookup}__"))

    # Deduplicate the final result, as embedded fields could overlap with _links.
    return sorted(set(lookups)) if not prefix else lookups


class ChunkedQuerySetIterator(Iterable[M]):
    """An optimal strategy to perform ``prefetch_related()`` on large datasets.

    It fetches data from the queryset in chunks,
    and performs ``prefetch_related()`` behavior on each chunk.

    Django's ``QuerySet.prefetch_related()`` works by loading the whole queryset into memory,
    and performing an analysis of the related objects to fetch. When working on large datasets,
    this is very inefficient as more memory is consumed. Instead, ``QuerySet.iterator()``
    is preferred here as it returns instances while reading them. Nothing is stored in memory.
    Hence, both approaches are fundamentally incompatible. This class performs a
    mixed strategy: load a chunk, and perform prefetches for that particular batch.

    As extra performance benefit, a local cache avoids prefetching the same records
    again when the next chunk is analysed. It has a "least recently used" cache to avoid
    flooding the caches when foreign keys constantly point to different unique objects.
    """

    def __init__(self, queryset: models.QuerySet, chunk_size=None, sql_chunk_size=None):
        """
        :param queryset: The queryset to iterate over, that has ``prefetch_related()`` data.
        :param chunk_size: The size of each segment to analyse in-memory for related objects.
        :param sql_chunk_size: The size of each segment to fetch from the database,
            used when server-side cursors are not available. The default follows Django behavior.
        """
        self.queryset = queryset
        self.sql_chunk_size = sql_chunk_size or DEFAULT_SQL_CHUNK_SIZE
        self.chunk_size = chunk_size or self.sql_chunk_size
        self._fk_caches = defaultdict(lambda: LRU(self.chunk_size // 2))

    def __iter__(self):
        # Using iter() ensures the ModelIterable is resumed with the next chunk.
        qs_iter = iter(self.queryset.iterator(chunk_size=self.sql_chunk_size))

        # Keep fetching chunks
        while instances := list(islice(qs_iter, self.chunk_size)):
            # Perform prefetches on this chunk:
            if self.queryset._prefetch_related_lookups:
                self._add_prefetches(instances)
            yield from instances

    def _add_prefetches(self, instances: List[M]):
        """Merge the prefetched objects for this batch with the model instances."""
        if self._fk_caches:
            # Make sure prefetch_related_objects() doesn't have to fetch items again
            # that infrequently changes (e.g. a "wijk" or "stadsdeel").
            all_restored = self._restore_caches(instances)
            if all_restored:
                return

        # Reuse the Django machinery for retrieving missing sub objects.
        # and analyse the ForeignKey caches to allow faster prefetches next time
        models.prefetch_related_objects(instances, *self.queryset._prefetch_related_lookups)
        self._persist_prefetch_cache(instances)

    def _persist_prefetch_cache(self, instances):
        """Store the prefetched data so it can be applied to the next batch"""
        for instance in instances:
            for lookup, obj in instance._state.fields_cache.items():
                if obj is not None:
                    cache = self._fk_caches[lookup]
                    cache[obj.pk] = obj

    def _restore_caches(self, instances) -> bool:
        """Restore prefetched data to the new set of instances.
        This avoids unneeded prefetching of the same ForeignKey relation.
        """
        if not instances:
            return True
        if not self._fk_caches:
            return False

        all_restored = True

        for lookup, cache in self._fk_caches.items():
            field = instances[0]._meta.get_field(lookup)
            for instance in instances:
                id_value = getattr(instance, field.attname)
                if id_value is None:
                    continue

                if (obj := cache.get(id_value, None)) is not None:
                    instance._state.fields_cache[lookup] = obj
                else:
                    all_restored = False

        return all_restored


class ObservableIterator(Iterator[T]):
    """Observe the objects that are being returned.

    Unlike itertools.tee(), retrieved objects are directly processed by other functions.
    As built-in feature, the number of returned objects is also counted.
    """

    def __init__(self, iterable: Iterable[T], observers=None):
        self.number_returned = 0
        self._iterable = iter(iterable)
        self._item_callbacks = list(observers) if observers else []
        self._has_items = None

    def add_observer(self, callback: Callable[[T], None]):
        """Install an observer callback that is notified when items are iterated"""
        self._item_callbacks.append(callback)

    def __iter__(self) -> ObservableIterator[T]:
        return self

    def __next__(self) -> T:
        """Keep a count of the returned items, and allow to notify other generators"""
        try:
            value = next(self._iterable)
        except StopIteration:
            self._is_iterated = True
            raise

        self.number_returned += 1
        self._has_items = True

        # Notify observers
        for notify_callback in self._item_callbacks:
            notify_callback(value)

        return value

    def __bool__(self):
        """Tell whether the generator would contain items."""
        if self._has_items is None:
            # Perform an inspection of the generator:
            first_item, items = peek_iterable(self._iterable)
            self._iterable = items
            self._has_items = first_item is not None

        return self._has_items


class EmbeddedResultSet(ReturnGenerator):
    """A wrapper for the returned expanded fields.
    This is used in combination with the ObservableIterator.

    The :func:`inspect_instance` is called each time an object is retrieved.
    As alternative, all instances *can* be provided at construction, which is
    typically useful for a detail page as this breaks streaming otherwise.
    """

    def __init__(
        self,
        embedded_field: AbstractEmbeddedField,
        serializer: serializers.Serializer,
        main_instances: Optional[list] = None,
        id_fetcher=None,
    ):
        # Embedded result sets always work on child elements,
        # as the source queryset is iterated over within this class.
        if isinstance(serializer, serializers.ListSerializer):
            serializer = serializer.child

        super().__init__(generator=None, serializer=serializer)
        self.embedded_field = embedded_field
        self.id_list = []
        self.id_fetcher = id_fetcher

        if id_fetcher is None and serializer.parent.id_based_fetcher:
            # Fallback to serializer based ID-fetcher if needed.
            self.id_fetcher = serializer.parent.id_based_fetcher(embedded_field)

        # Allow to pre-feed with instances (e.g for detail view)
        if main_instances is not None:
            for instance in main_instances:
                self.inspect_instance(instance)

    def inspect_instance(self, instance):
        """Inspect a main object to find any references for this embedded result."""
        ids = self.embedded_field.get_related_ids(instance)
        if ids:
            self.id_list.extend(ids)

    def get_objects(self) -> Iterator[models.Model]:
        """Retrieve the objects to render"""
        if self.id_fetcher is None:
            # Standard Django foreign-key like behavior.
            queryset = self.embedded_field.related_model.objects.filter(pk__in=self.id_list)
        else:
            # e.g. retrieve from a remote API, or filtered database table.
            queryset = self.id_fetcher(self.id_list)
            if not isinstance(queryset, models.QuerySet):
                return queryset  # may return an iterator, can't optimize

        return self.optimize_queryset(queryset)

    def optimize_queryset(self, queryset):
        """Optimize the queryset, see if N-query calls can be avoided."""
        lookups = get_serializer_lookups(self.serializer)
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

        return super().__iter__()  # returns iter(self.generator)

    def __bool__(self):
        if self.generator is None:
            self.generator = self._build_generator()
        return super().__bool__()

    def _build_generator(self):
        """Create the generator on-demand"""
        return (self.serializer.to_representation(instance) for instance in self.get_objects())
