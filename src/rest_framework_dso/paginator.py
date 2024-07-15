from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import TypeVar

from django.core.paginator import EmptyPage, PageNotAnInteger
from django.core.paginator import Page as DjangoPage
from django.core.paginator import Paginator as DjangoPaginator
from django.db.models.query import QuerySet
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from rest_framework_dso.embedding import ObservableIterator

Q = TypeVar("Q", bound=QuerySet)


class DSOPaginator(DjangoPaginator):
    """A paginator that supports streaming.

    This paginator avoids expensive count queries.
    So num_pages() is not supported.
    """

    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True):
        if orphans != 0:
            warnings.warn(
                "DSOPaginator instantiated with non-zero value in orphans. \
                    Orphans are not supported by this class and will be ignored.",
                RuntimeWarning,
                stacklevel=2,
            )
        super().__init__(object_list, per_page, 0, allow_empty_first_page)

    def validate_number(self, number):
        """Validate the given 1-based page number."""
        try:
            if isinstance(number, float) and not number.is_integer():
                raise ValueError
            number = int(number)
        except (TypeError, ValueError) as e:
            raise PageNotAnInteger(_("That page number is not an integer")) from e
        if number < 1:
            raise EmptyPage(_("That page number is less than 1"))
        return number

    def get_page(self, number):
        """
        Return a valid page, even if the page argument isn't a number or isn't
        in range.
        """
        try:
            number = self.validate_number(number)
        except PageNotAnInteger:
            number = 1
        return self.page(number)

    def page(self, number):
        """Return a Page object for the given 1-based page number."""
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page

        # One additional sentinel object, is given to the page.
        # This object should not be rendered, but it allows the page
        # to detect whether more items exist beyond it and hence wether a next page exists.
        sentinel = 1
        return self._get_page(self.object_list[bottom : top + sentinel], number, self)

    def _get_page(self, *args, **kwargs):
        """
        Return an instance of a single page.

        This hook can be used by subclasses to use an alternative to the
        standard :cls:`Page` object.
        """
        return DSOPage(*args, **kwargs)


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


class DSOPage(DjangoPage):
    """A page that can be streamed.

    This page avoids count queries by delaying calculation of the page length.

    The number of items on the page cannot be known before
    the object_list has been iterated.
    Therefore __len__ and has_next methods are only valid
    after the object list has been iterated.
    """

    def __init__(self, object_list, number, paginator):
        self.number = number
        self.paginator = paginator
        self._length = 0
        self._has_next = None
        self._object_list_iterator = None
        if isinstance(object_list, QuerySet):
            # We have to cast the queryset instance into an observable queryset here. Not pretty.
            # Pagination in DRF is handled early on in the pipeline where, because we stream the
            # data we don't know the number of items on the page.
            # We need the number of items to tell whether a next page exists.
            #
            # So we need to keep track of the iteration process happening in the renderer.
            # We can not create the iterator at this point, because streaming will break
            # further down the line if object_list is not a queryset
            # And we don't want to move all the pagination logic into the generic renderer.
            # So in order to watch the iterators created later on by the queryset we have to
            # wrap it here.
            self.object_list = ObservableQuerySet.from_queryset(
                object_list, [self._watch_object_list]
            )
        else:
            self.object_list = ObservableIterator(object_list, [self._watch_object_list])
            # Object list is empty
            if not self.object_list:
                self._watch_object_list(None, None, True)

    def __repr__(self):
        return f"<Page {self.number}>"

    def __len__(self):
        return self._length

    def has_next(self) -> bool | None:
        """There is a page after this one.
        Returns:
            True, if a next page exist.
            False, if a next page does not exist.
            None, if unknown.
        """
        if self.is_iterated():
            return self._has_next
        else:
            return None

    def is_iterated(self) -> bool:
        """Check whether the all objects on this page have been iterated,
        so the number of items on the page is known.
        """
        return self._object_list_iterator is not None and self._object_list_iterator.is_iterated()

    def _watch_object_list(
        self, item, observable_iterator: ObservableIterator = None, iterator_is_empty=False
    ):
        """Adjust page length and throw away the sentinel item"""

        # Make sure we are not iterating again.
        if self.is_iterated():
            return

        # Observable queryset returns the iterator
        # Observable iterator does not
        if observable_iterator is None:
            observable_iterator = self.object_list

        # Keep track of the iterator
        self._object_list_iterator = observable_iterator

        # If this is not page 1 and the object list is empty
        # user navigated beyond the last page so we throw a 404.
        if iterator_is_empty and self.number > 1:
            raise Http404()

        # Set the number of objects read up till now
        number_returned = observable_iterator.number_returned
        self._length = min(self.paginator.per_page, number_returned)

        # If the sentinel item was returned a next page exists
        self._has_next = number_returned > self.paginator.per_page

        # The page was passed an extra object in its object_list
        # as a sentinel to detect wether more items exist beyond this page
        # and hence a next page exists.
        # This object should not be rendered so we call next() again to stop the iterator.
        if observable_iterator.number_returned == self.paginator.per_page + 1:
            # Throw away the sentinel item
            next(observable_iterator)
