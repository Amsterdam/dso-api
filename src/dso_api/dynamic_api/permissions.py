from dataclasses import dataclass, field
from typing import Dict, Set

from cachetools.func import ttl_cache
from rest_framework import permissions
from schematools.contrib.django import models
from dso_api.dynamic_api.utils import snake_to_camel_case


@dataclass
class TableScopes:
    """OAuth scopes for tables and fields."""

    table: Set[str] = field(default_factory=set)
    fields: Dict[str, Set[str]] = field(default_factory=dict)


@ttl_cache(ttl=60 * 60)
def fetch_scopes_for_dataset_table(dataset_id: str, table_id: str):
    """ Get the scopes for a dataset and table, based on the Amsterdam schema information """

    def _fetch_scopes(obj):
        if obj.auth:
            return set(obj.auth.split(","))
        return set()

    try:
        table = models.DatasetTable.objects.get(name=table_id, dataset__name=dataset_id)
    except models.DatasetTable.DoesNotExist:
        return TableScopes()

    return TableScopes(
        table=_fetch_scopes(table) | _fetch_scopes(table.dataset),
        fields={field.name: _fetch_scopes(field) for field in table.fields.all()},
    )


@ttl_cache(ttl=60 * 60)
def fetch_scopes_for_model(model) -> TableScopes:
    """ Get the scopes for a Django model, based on the Amsterdam schema information """

    # If it is not a DSO-based model, we leave it alone
    if not hasattr(model, "_dataset_schema"):
        return TableScopes()
    table = model._table_schema.id
    dataset = model._meta.app_label

    return fetch_scopes_for_dataset_table(dataset, table)


def get_unauthorized_fields(request, model) -> set:
    """Check which field names should be excluded"""
    scope_data = fetch_scopes_for_model(model).fields

    unauthorized_fields = set()
    # is_authorized_for is added by authorization_django middleware
    if hasattr(request, "is_authorized_for"):
        for model_field in model._meta.get_fields():
            scopes = scope_data.get(model_field.name)
            if not scopes:
                continue

            if not request.is_authorized_for(*scopes):
                unauthorized_fields.add(snake_to_camel_case(model_field.name))

    return unauthorized_fields


class HasOAuth2Scopes(permissions.BasePermission):
    """
    Custom permission to check auth scopes from Amsterdam schema.
    """

    def _has_permission(self, request, model=None, dataset_id=None, table_id=None):
        if request.method == "OPTIONS":
            return True
        if model:
            scopes = fetch_scopes_for_model(model)
        elif dataset_id and table_id:
            scopes = fetch_scopes_for_dataset_table(dataset_id, table_id)
        return request.is_authorized_for(*scopes.table)

    def has_permission(self, request, view, models=None):
        """ Based on the model that is associated with the view
            the Dataset and DatasetTable (if available)
            are check for their 'auth' field.
            These auth fields could contain a komma-separated list
            of claims. """
        if models:
            for model in models:
                if not self._has_permission(request, model):
                    return False
            return True
        elif hasattr(view, "dataset_id") and hasattr(view, "table_id"):
            return self._has_permission(
                request, dataset_id=view.dataset_id, table_id=view.table_id
            )
        else:
            model = view.get_serializer_class().Meta.model
            return self._has_permission(request, model=model)

    def has_object_permission(self, request, view, obj):
        """ This method is not called for list views """
        # XXX For now, this is OK, later on we need to add row-level permissions
        return self._has_permission(request, obj)
