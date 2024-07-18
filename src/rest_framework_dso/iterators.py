"""Some advanced interator stuff going on here.

Most of our datasets are huge, and fetching them all in memory is impossible or very slow.
Instead, everything is streamed to the output. However, often information does need to
be collected during this iteration, and relations need to be fetched as well.

This module implements the classes to aid this functionality.
It allows watching and inspecting the results during iteration, and altering them.

This includes:

* :class:`ObservableIterator` inspect each item during iteration.
* :class:`ObservableQuerySet` applies this logic to querysets.
* :class:`ChunkedQuerySetIterator` allows prefetching objects on iterated chunks.
"""

from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from functools import lru_cache
from itertools import islice
from typing import TypeVar

from django.db import models
from django.db.models.query import QuerySet
from lru import LRU

Q = TypeVar("Q", bound=QuerySet)
M = TypeVar("M", bound=models.Model)
T = TypeVar("T")

logger = logging.getLogger(__name__)

DEFAULT_SQL_CHUNK_SIZE = 2000  # allow unit tests to alter this.


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
        chunk_id = 0

        # Keep fetching chunks
        while instances := list(islice(qs_iter, self.chunk_size)):
            # Perform prefetches on this chunk:
            if self.queryset._prefetch_related_lookups:
                self._add_prefetches(instances, chunk_id)
                chunk_id += 1

            yield from instances

    def _add_prefetches(self, instances: list[M], chunk_id):
        """Merge the prefetched objects for this batch with the model instances."""
        if self._fk_caches:
            # Make sure prefetch_related_objects() doesn't have to fetch items again
            # that infrequently changes (e.g. a "wijk" or "stadsdeel").
            all_restored = self._restore_caches(instances)
            if all_restored:
                logger.debug("[chunk %d] No additional prefetched needed.", chunk_id)
                return

        logger.debug("[chunk %d] Prefetching related objects...", chunk_id)

        # Reuse the Django machinery for retrieving missing sub objects.
        # and analyse the ForeignKey caches to allow faster prefetches next time
        models.prefetch_related_objects(instances, *self.queryset._prefetch_related_lookups)
        self._persist_prefetch_cache(instances)
        logger.debug("[chunk %d] ...done prefetching related objects.", chunk_id)

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

        if all_restored:
            logger.debug("All prefetches restored from cache")

        return all_restored


@lru_cache
def _create_observable_queryset_subclass(
    queryset_class: type[Q],
) -> type[Q] | type[ObservableQuerySet]:
    """Insert the ObservableQuerySet into a QuerySet subclass, as if it's a mixin.
    This creates a custom subclass, that inherits both ObservableQuerySet and the QuerySet class.

    Otherwise, custom methods on the queryset class are lost after
    wrapping the queryset into an observable queryset,
    """
    if queryset_class is QuerySet:
        # No need to create a custom class.
        return ObservableQuerySet
    else:
        # Extend from both:
        name = queryset_class.__name__.replace("QuerySet", "") + "ObservableQuerySet"
        return type(name, (ObservableQuerySet, queryset_class), {})


class ObservableQuerySet(QuerySet):
    """A QuerySet that has observable iterators.

    This class overloads the iterator and __iter__ methods
    and wraps the iterators returned by the base class
    in ObservableIterators.

    All QuerySet methods that return another QuerySet,
    return an ObservableQuerySet with the same observers
    as the parent instance.

    Observers added to an instance will be notified of
    iteration events on the last iterator created by
    the instance.
    """

    def __init__(self, *args, **kwargs):
        self._item_callbacks: list[Callable] = []
        self._obs_iterator: ObservableIterator = None
        super().__init__(*args, **kwargs)

    @classmethod
    def from_queryset(cls, queryset: QuerySet, observers: list[Callable] | None = None):
        """Turn a QuerySet instance into an ObservableQuerySet"""
        queryset.__class__ = _create_observable_queryset_subclass(queryset.__class__)
        queryset._item_callbacks = list(observers) if observers else []
        queryset._obs_iterator = None
        return queryset

    def _clone(self, *args, **kwargs):
        """Clone this instance, including its observers.
        So any iterators created by the clone will also call
        the observers.
        """
        # It's not classy to touch privates, but we want to observe
        # iteration on all chained objects as well.
        # The _clone() method is used by Django in all methods
        # that return another QuerySet, like filter() and prefetch_related().
        # Overloading this method handles all of those in one go.
        clone = super()._clone(*args, **kwargs)
        clone._item_callbacks = self._item_callbacks.copy()
        return clone

    def iterator(self, *args, **kwargs):
        """Return observable iterator and add observer.
        Wraps an observable iterator around the iterator
        returned by the base class.
        """
        iterator = super().iterator(*args, **kwargs)
        return self._wrap_iterator(iterator)

    def __iter__(self):
        """Return observable iterator and add observer.
        Wraps an observable iterator around the iterator
        returned by the base class.
        """
        return self._wrap_iterator(super().__iter__())

    def _wrap_iterator(self, iterator: Iterable) -> ObservableIterator:
        """Wrap an iterator inside an ObservableIterator"""
        iterator = ObservableIterator(iterator)
        iterator.add_observer(self._item_observer)

        # Remove observer from existing oberservable iterator
        if self._obs_iterator is not None:
            self._obs_iterator.clear_observers()

        self._obs_iterator = iterator

        # Notify observers of empty iterator
        if not iterator:
            self._item_observer(None, True)

        return iterator

    def _item_observer(self, item, is_empty=False):
        """Notify all observers."""
        for callback in self._item_callbacks:
            callback(item, self._obs_iterator, is_empty)


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
        self._is_iterated = False

    def add_observer(self, callback: Callable[[T], None]):
        """Install an observer callback that is notified when items are iterated"""
        self._item_callbacks.append(callback)

    def clear_observers(self):
        """Remove all observers"""
        self._item_callbacks = []

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

    def is_iterated(self):
        """Tell whether the iterator has finished."""
        return self._is_iterated

    def __bool__(self):
        """Tell whether the generator would contain items."""
        if self._has_items is None:
            # Perform an inspection of the generator:
            first_item, items = peek_iterable(self._iterable)
            self._iterable = items
            self._has_items = first_item is not None

        return self._has_items


def peek_iterable(generator):
    """Take a quick look at the first item of a generator/iterable.
    This returns a modified iterable that contains all elements, including the peeked item.
    """
    iterable = iter(generator)  # make sure this is an iterator, so it can't restart.
    try:
        item = next(iterable)
    except StopIteration:
        return None, iterable

    return item, itertools.chain([item], iterable)
