"""Adapter classes for Django REST Framework.

The "filter backend" classes follow an API of Django REST Framework,
that allows adapting the QuerySet before the view/serializer starts.
This gives a chance to add filtering and ordering to the queryset.
"""
from __future__ import annotations

from rest_framework.filters import BaseFilterBackend, OrderingFilter

from dso_api.dynamic_api.filters import openapi
from dso_api.dynamic_api.filters.parser import QueryFilterEngine


class DynamicFilterBackend(BaseFilterBackend):
    """A backend that performs filtering backed on query-string parameters.

    Usage in views::

        class View(GenericAPIView):
            filter_backends = [filters.DynamicFilterBackend]
    """

    def filter_queryset(self, request, queryset, view):
        """Filter the queryset of the view.
        This hook function is called by Django REST Framework
        to apply this filter backend on the constructed queryset.
        """
        engine = QueryFilterEngine.from_request(request)
        return engine.filter_queryset(queryset)

    def get_schema_operation_parameters(self, view):
        """Generate the OpenAPI fragments for the filter parameters.
        This hook function is called by Django REST Framework
        to generate the OpenAPI data.
        """
        return openapi.get_table_filter_params(view.table_schema)


class DynamicOrderingFilter(OrderingFilter):
    """Ordering filter, following the DSO spec.

    This adds an ``?_sort=<fieldname>,-<desc-fieldname>`` option to the view.
    Usage in views::

        class View(GenericAPIView):
            filter_backends = [filters.DynamicOrderingFilter]
    """

    ordering_param = "_sort"  # Enforce DSO-specific name.

    def get_ordering(self, request, queryset, view):
        if self.ordering_param not in request.query_params:
            # Allow DSO 1.0 Dutch "sorteer" parameter
            # Can adjust 'self' as this instance is recreated each request.
            if "sorteer" in request.query_params:
                self.ordering_param = "sorteer"

        ordering = super().get_ordering(request, queryset, view)
        if ordering is None:
            return ordering

        # Convert identifiers to snake_case, preserving `-` (descending sort).
        # The to_orm_path() already checks the user scopes for field access.
        # That prevents leaking data of inaccessible fields (e.g. by sorting on a boolean field)
        return [
            "-" + QueryFilterEngine.to_orm_path(part[1:], view.table_schema, request.user_scopes)
            if part.startswith("-")
            else QueryFilterEngine.to_orm_path(part, view.table_schema, request.user_scopes)
            for part in ordering
        ]

    def remove_invalid_fields(self, queryset, fields, view, request):
        # No need to validate, or create a serializer.
        # The validation already happens inside to_orm_path()
        #
        # Default Django REST Framework behavior is to check `view.ordering_fields`, or
        # use "serializer_class().fields.keys()" to find which fields are permitted.
        #
        # Since the filters also supports spanning relationships, precalculating the allowed
        # fields is nearly impossible and inefficient. Instead, to_orm_path() validates
        # whether the actual followed path is permitted for the user.
        return fields
