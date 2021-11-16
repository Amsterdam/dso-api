"""This implements the backend for filtering, sorting and wildcard search.
The implementation is based on `django-filter`_
which does the heavy lifting of argument parsing and processing.

There are 2 distinct object types: a "filter set backend" and "filter set".

**Backends**, like the  :class:`~rest_framework_dso.filters.DSOFilterBackend`
and :class:`~rest_framework_dso.filters.DSOOrderingFilter` are linked
into the standard Django REST Framework logic for "filter backends".
Those classes receive the Django :class:`~django.models.db.QuerySet` and
can filter/manipulate it. The backends can be defined globally for all views
using ``REST_FRAMEWORK["DEFAULT_FILTER_BACKENDS"]``, per on a per-view basis
with ``filter_backends``.

**Filtersets** are an invention from `django-filter`_. These are linked to the view with
the ``filterset_class`` attribute to define *what* the ``FilterSetBackend``
should parse and filter. Those filtersets are all implemented as subclasses
of :class:`DSOFilterSet`.

In code, this works as following:

.. code-block:: python

    class View(GenericAPIView):
        # Standard Django REST Framework logic:
        filter_backends = [DSOFilterBackend, DSOOrderingFilter]

        # Additional attribute for the filter backend.
        filterset_class = [...]  # list of DSOFilterSet subclasses

Filterset internals
-------------------

Internally, `django-filter`_ works by constructing a Django form object based on the filters.
The form parses the request using standard widgets, and returns the "cleaned data" like any
other Django form. The `django-filter`_ classes use that parsed data to filter the queryset.
The basic design:

.. graphviz::

    digraph foo {
        rankdir = LR;

        filtersetbackend_queryset [label=".filter_queryset()" shape=none]
        filterset_queryset [label=".filter_queryset()" shape=none]
        filter_queryset [label=".filter()" shape=none]

        FilterSetBackend -> FilterSet [label="view.filterset_class" style=bold]
        FilterSet -> Filter [label=".fields"]

        Filter -> Field [label="field_class" style=bold]
        FilterSet -> Form [label=".form"]
        Form -> Field [label=".fields"]
        Field -> Widget [label="widget" style=bold]

        // Show related queryset call flow.
        {rank=same; FilterSetBackend -> filtersetbackend_queryset [style=invis]}
        {rank=same; FilterSet -> filterset_queryset [style=invis]}
        {rank=same; Filter -> filter_queryset [style=invis]}

        filtersetbackend_queryset -> filterset_queryset
        filterset_queryset -> filter_queryset
    }

|

The ``FilterSet`` can hold many filters, even for the same field.
For example, queries for ``?name=``, ``?name[in]=..`` and ``?name[not]=...`` are all
handled by separate ``Filter`` instances in the ``FilterSet``.
The filter class is the same, but it will be instantiated with different ``lookup_expr``.

Each ``Filter`` field provides a standard Django form field.
This way, the ``FilterSet`` can generate a standard Django form
to parse the input from the ``request.GET``.
Django forms use widgets to retrieve the field data,
and form fields to validate and translate the input.

With the validated input, the ``FilterSet`` asks each ``Filter`` to update the
Django :class:`~django.db.models.QuerySet` accordingly. This performs the actual filtering.
To generate the proper SQL statements for operators such as ``NOT`` or ``LIKE``,
additional lookup classes are implemented that provide this functionality within the Django ORM.

.. _django-filter: https://django-filter.readthedocs.io/
"""
from . import lookups  # noqa (import is needed for registration)
from .backends import DSOFilterBackend, DSOOrderingFilter
from .filters import MultipleValueFilter
from .filtersets import DSOFilterSet

__all__ = [
    "DSOFilterSet",
    "DSOFilterBackend",
    "DSOOrderingFilter",
    "MultipleValueFilter",
]
