"""This implements the backend for filtering, sorting and wildcard search.
The implementation is based on `django-filter`_
which does the heavy lifting of argument parsing and processing.

There are 2 distinct object types: a "filter set backend" and "filter set".
Backends, like the  :class:`DSOFilterSetBackend` and :class:`DSOOrderingFilter` are linked
into the standard Django REST Framework logic for ``filter_backends``.
Those classes receive the Django :class:`~django.models.db.QuerySet` and
can filter/manipulate it.

On this of this, `django-filter`_ introduces the ``filterset_class`` attribute
to define *what* the ``FilterSetBackend`` should parse and filter.
Those filtersets are all implemented as subclasses of :class:`DSOFilterSet`.

In code, this works as following:

.. code-block:: python

    class View(GenericAPIView):
        # Standard Django REST Framework logic:
        filter_backends = [filters.DSOFilterSetBackend, DSOOrderingFilter]

        # Additional attribute for the filterset backend.
        filterset_class = [...]  # list of DSOFilterSet subclasses

Internally, `django-filter`_ works by constructing a Django form object based on the filters.
The form parses the request using standard widgets, and returns the "cleaned data"
like any other Django form. The "filter fields" then use this to adjust the queryset.

Hence, you'll find widgets, "filter fields" and ORM lookup subclasses in this file too.

.. _django-filter: https://django-filter.readthedocs.io/
"""
from . import lookups  # noqa (import is needed for registration)
from .backends import DSOFilterSetBackend, DSOOrderingFilter
from .filters import MultipleValueFilter, RangeFilter
from .filtersets import DSOFilterSet

__all__ = [
    "DSOFilterSet",
    "DSOFilterSetBackend",
    "DSOOrderingFilter",
    "RangeFilter",
    "MultipleValueFilter",
]
