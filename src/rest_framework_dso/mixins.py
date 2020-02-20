from __future__ import annotations

from typing import Type


class DSOFilterMixin:
    """View/Viewset mixin that adds DSO-compatible filtering.

    This adds default filter backends in the view for sorting and filtering.
    The filtering logic is delegated to a ``filterset_class`` by django-filter.

    * Set ``filterset_class`` to enable filtering on fields.
    * The ``ordering_fields`` can be set on the view as well.
      By default, it accepts all serializer field names as input.
    """

    # Using standard fields
    filter_backends = [filters.DSOFilterSetBackend, filters.DSOOrderingFilter]

    #: Class to configure the filterset
    #: (auto-generated when filterset_fields is defined, but this is slower).
    filterset_class: Type[filters.DSOFilterSet] = None
