from cachetools.func import ttl_cache
from rest_framework import permissions
from dso_api.datasets import models


@ttl_cache(ttl=60 * 60)
def fetch_scopes_for_model(model):
    """ Get the scopes for a Django model, based on the Amsterdam schema information """

    def _fetch_scopes(obj):
        if obj.auth:
            return set(obj.auth.split(","))
        return set()

    default_value = dict(table=set(), field={})
    # If it is not a DSO-based model, we leave it alone
    if not hasattr(model, "_dataset_schema"):
        return default_value
    dataset_table = model._dataset_schema.get_table_by_id(model._meta.model_name)
    try:
        table = models.DatasetTable.objects.get(name=dataset_table.id)
    except models.DatasetTable.DoesNotExist:
        return default_value

    return {
        "table": _fetch_scopes(table) | _fetch_scopes(table.dataset),
        "field": {field.name: _fetch_scopes(field) for field in table.fields.all()},
    }


class HasSufficientScopes(permissions.BasePermission):
    """
    Custom permission to check auth scopes from Amsterdam schema.
    """

    def has_permission(self, request, view):
        """ Based on the model that is associated with the view
            the Dataset and DatasetTable (if available)
            are check for their 'auth' field.
            These auth fields could contain a komma-separated list
            of claims. """

        model = view.serializer_class.Meta.model
        scopes = fetch_scopes_for_model(model)
        return request.is_authorized_for(*scopes["table"])

    def has_object_permission(self, request, view, obj):
        """ This method is not called for list views """
        # XXX For now, this is OK, later on we need to add row-level permissions
        return True
