"""Logic to implement object embedding, and retrieval in a streaming-like fashion.

It's written in an observer/listener style, allowing the embedded data to be determined
during the rendering. Instead of having to load the main results in memory for analysis,
the main objects are inspected while they are consumed by the output stream.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import islice
from typing import Callable, Dict, Iterable, Iterator, List, Optional, TypeVar, Union

from django.db import models
from lru import LRU
from rest_framework import serializers
from rest_framework.exceptions import ParseError, PermissionDenied

from dso_api.dynamic_api.permissions import fetch_scopes_for_model
from rest_framework_dso.fields import AbstractEmbeddedField, EmbeddedField
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable

EmbeddedFieldDict = Dict[str, AbstractEmbeddedField]
T = TypeVar("T")
M = TypeVar("M", bound=models.Model)
DEFAULT_SQL_CHUNK_SIZE = 2000  # allow unit tests to alter this.


def get_expanded_fields(  # noqa: C901
    parent_serializer: serializers.Serializer, fields_to_expand: Union[List[str], bool]
) -> Dict[str, EmbeddedField]:
    """Find the expanded fields in a serializer that are requested.
    This translates the ``_expand`` query into a dict of embedded fields.
    """
    if not fields_to_expand:
        return {}

    allowed_names = getattr(parent_serializer.Meta, "embedded_fields", [])
    auth_checker = getattr(parent_serializer, "get_auth_checker", lambda: None)()
    embedded_fields = {}

    # ?_expand=true should expand all names
    auto_expand_all = fields_to_expand is True
    if auto_expand_all:
        fields_to_expand = allowed_names

    for field_name in fields_to_expand:
        if field_name not in allowed_names:
            raise _expand_parse_error(allowed_names, field_name) from None

        # Get the field
        try:
            field = getattr(parent_serializer, field_name)
        except AttributeError:
            raise RuntimeError(
                f"{parent_serializer.__class__.__name__}.{field_name}"
                f" does not refer to an embedded field."
            ) from None

        # Check access via scopes (NOTE: this is higher-level functionality)
        scopes = fetch_scopes_for_model(field.related_model)
        if auth_checker and not auth_checker(*scopes.table):
            # Not allowed, silently drop for _expand=true request.
            if auto_expand_all:
                continue

            # Explicitly mentioned, raise error.
            raise PermissionDenied(f"Eager loading not allowed for field '{field_name}'")

        embedded_fields[field_name] = field

    return embedded_fields


def _expand_parse_error(allowed_names, field_name):
    """Generate the proper exception for the invalid expand name"""
    available = ", ".join(sorted(allowed_names))
    if not available:
        return ParseError("Eager loading is not supported for this endpoint")
    else:
        return ParseError(
            f"Eager loading is not supported for field '{field_name}', "
            f"available options are: {available}"
        )


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
        embedded_field: EmbeddedField,
        serializer: serializers.Serializer,
        main_instances: Optional[list] = None,
        id_fetcher=None,
    ):
        super().__init__(generator=None, serializer=serializer)
        self.embedded_field = embedded_field
        self.id_list = []
        self.id_fetcher = id_fetcher

        if id_fetcher is None and serializer.parent.id_based_fetcher:
            # Fallback to serializer based ID-fetcher if needed.
            self.id_fetcher = serializer.parent.id_based_fetcher(
                model=embedded_field.related_model, is_loose=embedded_field.is_loose
            )

        # Allow to pre-feed with instances (e.g for detail view)
        if main_instances is not None:
            for instance in main_instances:
                self.inspect_instance(instance)

    def inspect_instance(self, instance):
        """Inspect a main object to find any references for this embedded result."""
        ids = self.embedded_field.get_related_ids(instance)
        if ids:
            self.id_list.extend(ids)

    def get_objects(self):
        """Retrieve the objects to render"""
        if self.id_fetcher is not None:
            # e.g. retrieve from a remote API, or filtered database table.
            return self.id_fetcher(self.id_list)
        else:
            # Standard Django foreign-key like behavior.
            model = self.embedded_field.related_model
            return model.objects.filter(pk__in=self.id_list).iterator()

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
