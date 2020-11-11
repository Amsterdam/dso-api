from dataclasses import dataclass, field
from typing import Dict, Set

from cachetools.func import ttl_cache
from django.contrib.auth.models import AnonymousUser, _user_has_perm
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

            permission_key = get_permission_key_for_field(model_field)
            if not request.is_authorized_for(*scopes):
                if not request_has_permission(request=request, perm=permission_key):
                    unauthorized_fields.add(snake_to_camel_case(model_field.name))

    return unauthorized_fields


class MandatoryFiltersQueried(permissions.BasePermission):
    """
    Custom permission to check if there are any mandatory queries that need to be queried
    """

    def _mandatory_filtersets_queried(self, request, mandatory_filtersets):
        """Checks if any of the mandatory filtersets was used in the query paramaters"""
        valid_query_params = [
            param for param, value in request.query_params.items() if value
        ]

        def _mandatory_filterset_was_queried(mandatory_filterset, query_params):
            return all(
                mandatory_filter in query_params
                for mandatory_filter in mandatory_filterset
            )

        return any(
            _mandatory_filterset_was_queried(mandatory_filterset, valid_query_params)
            for mandatory_filterset in mandatory_filtersets
        )

    def has_permission(self, request, view):
        if request.method == "OPTIONS":
            return True
        scopes = fetch_scopes_for_dataset_table(view.dataset_id, view.table_id)
        authorized_by_scope = request.is_authorized_for(*scopes.table)
        if authorized_by_scope:
            return True
        mandatory_filtersets = []
        # TODO: remove RequestProfile initialization after auth_profile_middleware merge
        from schematools.contrib.django.auth_backend import RequestProfile

        auth_profile = RequestProfile(request)
        mandatory_filtersets += auth_profile.get_mandatory_filtersets(
            view.dataset_id, view.table_id
        )
        if mandatory_filtersets:
            return self._mandatory_filtersets_queried(request, mandatory_filtersets)
        return True


class HasOAuth2Scopes(permissions.BasePermission):
    """
    Custom permission to check auth scopes from Amsterdam schema.
    """

    def _has_permission(self, request, dataset_id=None, table_id=None):
        if request.method == "OPTIONS":
            return True
        scopes = fetch_scopes_for_dataset_table(dataset_id, table_id)
        if request.is_authorized_for(*scopes.table):
            return True  # authorized by scope
        else:
            # TODO: remove RequestProfile initialization after auth_profile_middleware merge
            from schematools.contrib.django.auth_backend import RequestProfile

            auth_profile = RequestProfile(request)
            relevant_profiles = auth_profile.get_relevant_profiles(dataset_id, table_id)
            if relevant_profiles:
                return True
        return False

    def has_permission(self, request, view, models=None):
        """Based on the model that is associated with the view
        the Dataset and DatasetTable (if available)
        are check for their 'auth' field.
        These auth fields could contain a komma-separated list
        of claims."""
        if models:
            for model in models:
                if not self._has_permission(
                    request,
                    dataset_id=model._dataset_schema["id"],
                    table_id=model._table_schema["id"],
                ):
                    return False
            return True
        elif hasattr(view, "dataset_id") and hasattr(view, "table_id"):
            return self._has_permission(
                request, dataset_id=view.dataset_id, table_id=view.table_id
            )
        else:
            model = view.get_serializer_class().Meta.model
            return self._has_permission(
                request,
                dataset_id=model._dataset_schema["id"],
                table_id=model._table_schema["id"],
            )

    def has_object_permission(self, request, view, obj):
        """ This method is not called for list views """
        # XXX For now, this is OK, later on we need to add row-level permissions
        return self._has_permission(request, obj)


def get_permission_key_for_field(model_field):
    model = model_field.model
    return models.generate_permission_key(
        model._meta.app_label, model._meta.model_name, model_field.name
    )


def request_has_permission(request, perm, obj=None):
    """Checks if request has permission by using authentication backend."""
    if not hasattr(request, "user") or request.user is None:
        request.user = AnonymousUser()

    if not hasattr(request.user, "request"):
        # Backport request in order to get ProfileAuthBackend working
        request.user.request = request

    return _user_has_perm(request.user, perm, obj)
