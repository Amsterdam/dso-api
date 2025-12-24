"""
This is heavily inspired by [drf-extensions@v0.8.0](https://github.com/chibisov/drf-extensions),
which technically doesn't support the latest version of django-rest-framework.

Changes with respect to that library:
    - added typing
    - removed some unnecessary transformations (for our setup)
    - minor alterations in code structure
"""

from typing import Any, Protocol

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import Http404
from rest_framework.routers import DefaultRouter

PARENT_LOOKUP = "parent_lookup_"


class NestedRegistryItem:
    def __init__(self, router, parent_prefix, parent_item=None, parent_viewset=None):
        self.router = router
        self.parent_prefix = parent_prefix
        self.parent_item = parent_item
        self.parent_viewset = parent_viewset

    def register(self, prefix, viewset, basename, parents_query_lookups):
        self.router._register(
            prefix=self.get_prefix(
                current_prefix=prefix, parents_query_lookups=parents_query_lookups
            ),
            viewset=viewset,
            basename=basename,
        )
        return NestedRegistryItem(
            router=self.router, parent_prefix=prefix, parent_item=self, parent_viewset=viewset
        )

    def get_prefix(self, current_prefix, parents_query_lookups):
        return f"{self.get_parent_prefix(parents_query_lookups)}/{current_prefix}"

    def get_parent_prefix(self, parents_query_lookups):
        prefix = "/"
        current_item = self
        i = len(parents_query_lookups) - 1
        while current_item:
            parent_lookup_value_regex = getattr(
                current_item.parent_viewset, "lookup_value_regex", "[^/.]+"
            )
            prefix = (
                f"{current_item.parent_prefix}/(?P<{PARENT_LOOKUP}{parents_query_lookups[i]}>"
                f"{parent_lookup_value_regex})/{prefix}"
            )
            i -= 1
            current_item = current_item.parent_item
        return f"/{prefix.strip('/')}"


class NestedRouterProtocol(Protocol):
    @property
    def registry(self) -> list[tuple[str, str]]: ...

    def register(self, *args, **kwargs) -> NestedRegistryItem: ...
    def _register(self, *args, **kwargs) -> NestedRegistryItem: ...


class NestedRouterMixin:
    def _register(self: NestedRouterProtocol, *args, **kwargs):
        return super().register(*args, **kwargs)

    def register(self: NestedRouterProtocol, *args, **kwargs):
        self._register(*args, **kwargs)
        return NestedRegistryItem(
            router=self, parent_prefix=self.registry[-1][0], parent_viewset=self.registry[-1][1]
        )


class NestedDefaultRouter(NestedRouterMixin, DefaultRouter):
    pass


class NestedViewSetProtocol(Protocol):
    @property
    def kwargs(self) -> dict[str, Any]: ...

    def get_parents_query_dict(self) -> dict: ...
    def filter_queryset_by_parents_lookups(self, qs) -> QuerySet: ...


class NestedViewSetMixin:
    def get_queryset(self: NestedViewSetProtocol) -> QuerySet:
        return self.filter_queryset_by_parents_lookups(super().get_queryset())

    def filter_queryset_by_parents_lookups(
        self: NestedViewSetProtocol, queryset: QuerySet
    ) -> QuerySet:
        parents_query_dict = self.get_parents_query_dict()
        if parents_query_dict:
            try:
                return queryset.filter(**parents_query_dict)
            except (ValueError, ValidationError):
                raise Http404 from None
        else:
            return queryset

    def get_parents_query_dict(self: NestedViewSetProtocol) -> dict[str, Any]:
        result = {}
        for kwarg_name, kwarg_value in self.kwargs.items():
            if kwarg_name.startswith(PARENT_LOOKUP):
                query_lookup = kwarg_name.replace(PARENT_LOOKUP, "", 1)
                result[query_lookup] = kwarg_value
        return result
