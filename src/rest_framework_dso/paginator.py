import warnings

from django.core.paginator import EmptyPage, PageNotAnInteger
from django.core.paginator import Page as DjangoPage
from django.core.paginator import Paginator as DjangoPaginator
from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import NotFound

from rest_framework_dso.iterators import ObservableIterator, ObservableQuerySet


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
        # to detect whether more items exist beyond it and hence whether a next page exists.
        sentinel = 1
        return self._get_page(self.object_list[bottom : top + sentinel], number, self)

    def _get_page(self, *args, **kwargs):
        """
        Return an instance of a single page.

        This hook can be used by subclasses to use an alternative to the
        standard :cls:`Page` object.
        """
        return DSOPage(*args, **kwargs)


class DSOPage(DjangoPage):
    """A page that can be streamed.

    This page avoids count queries by delaying calculation of the page length.

    The number of items on the page cannot be known before
    the object_list has been iterated.
    Therefore __len__ and has_next methods are only valid
    after the object list has been iterated.
    """

    def __init__(self, object_list, number, paginator):
        super().__init__([], number=number, paginator=paginator)
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
                object_list, [self._watch_object_list], [self._empty_object_list]
            )
        else:
            self.object_list = ObservableIterator(
                object_list, [self._watch_object_list], [self._empty_object_list]
            )

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

    def _watch_object_list(self, item, observable_iterator: ObservableIterator):
        """Adjust page length and throw away the sentinel item"""
        if self.is_iterated():
            # Make sure we are not iterating again.
            return

        # Keep track of the iterator
        self._object_list_iterator = observable_iterator

        # Set the number of objects read up till now
        number_retrieved = observable_iterator.number_returned
        self._length = min(self.paginator.per_page, number_retrieved)

        # If the sentinel item was returned a next page exists
        self._has_next = number_retrieved > self.paginator.per_page

        # The page was passed an extra object in its object_list
        # as a sentinel to detect whether more items exist beyond this page
        # and hence a next page exists.
        # This object should not be rendered so we call next() again to stop the iterator.
        if number_retrieved == self.paginator.per_page + 1:
            # Throw away the sentinel item
            next(observable_iterator)

    def _empty_object_list(self, observable_iterator: ObservableIterator):
        # Normally the PageNumberPagination.paginate_queryset() will detect the empty page,
        # and raise InvalidPage -> NotFound.
        if self.number > 1:
            raise NotFound(_("Invalid page."))
