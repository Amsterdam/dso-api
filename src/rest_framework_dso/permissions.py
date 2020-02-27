from rest_framework import permissions
from dso_api.datasets import models


class HasSufficientScopes(permissions.BasePermission):
    """
    Custom permission to check auth scopes from Amsterdam schema.
    """

    def _fetch_scopes(self, obj):
        if obj.auth:
            return set(obj.auth.split(","))
        return set()

    def has_permission(self, request, view):
        """ Based on the model that is associated with the view
            the Dataset and DatasetTable (if available)
            are check for their 'auth' field.
            These auth fields could contain a komma-separated list
            of claims. """

        model = view.get_serializer().Meta.model
        # If it is not a DSO=based model, we leave it alone
        if not hasattr(model, "_dataset_schema"):
            return True
        dataset_table = model._dataset_schema.get_table_by_id(model._meta.model_name)
        try:
            table = models.DatasetTable.objects.get(name=dataset_table.id)
        except models.DatasetTable.DoesNotExist:
            return True
        scopes = self._fetch_scopes(table) | self._fetch_scopes(table.dataset)
        return request.is_authorized_for(*scopes)

    def has_object_permission(self, request, view, obj):
        # XXX For now, this is OK, later on we need to add row-level permissions
        return True
