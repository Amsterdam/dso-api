import logging

from django.core.exceptions import PermissionDenied
from rest_framework import permissions
from rest_framework.viewsets import ViewSetMixin
from schematools.permissions import UserScopes
from schematools.types import DatasetFieldSchema

from rest_framework_dso.embedding import EmbeddedFieldMatch
from rest_framework_dso.serializers import ExpandableSerializer

audit_log = logging.getLogger("dso_api.audit")


def log_access(request, access: bool):
    if access:
        audit_log.info(
            "%s %s: access granted with %s",
            request.method,
            request.path,
            request.user_scopes,
        )
    else:
        audit_log.info(
            "%s %s: access denied with %s",
            request.method,
            request.path,
            request.user_scopes,
        )


def check_filter_field_access(field_name: str, field: DatasetFieldSchema, user_scopes: UserScopes):
    """Check whether the field ca be used for filtering."""
    if not user_scopes.has_field_access(field):
        raise PermissionDenied(f"Access denied to filter on: {field_name}")

    if field.related_field_ids is not None:
        # Check if related ID fields are accessible.
        for related_id_field in field.related_fields:
            if not user_scopes.has_field_access(related_id_field):
                raise PermissionDenied(f"Access denied to filter on: {field_name}")


def filter_unauthorized_expands(
    user_scopes: UserScopes, expanded_fields: list[EmbeddedFieldMatch], skip_unauth=False
) -> list[EmbeddedFieldMatch]:
    """Remove expanded fields if these are not accessible"""

    result = []
    for match in expanded_fields:
        field_perm = user_scopes.has_field_access(match.field.field_schema)
        table_perm = user_scopes.has_table_fields_access(match.field.related_model.table_schema())
        if field_perm and table_perm:
            # Only add the field when there is permission
            result.append(match)

            # When there is nested expanding, perform an early check for nested fields.
            # Otherwise, the checks happen on-demand during streaming response rendering.
            if not skip_unauth and match.nested_expand_scope:
                embedded_serializer = match.embedded_serializer
                if isinstance(embedded_serializer, ExpandableSerializer):
                    filter_unauthorized_expands(
                        user_scopes, embedded_serializer.expanded_fields, skip_unauth
                    )
        else:
            if skip_unauth:
                # Not allowed, but can silently drop for "auto expand all"
                continue

            # Explicitly mentioned, raise error.
            raise PermissionDenied(f"Eager loading not allowed for field '{match.full_name}'")

    return result


class HasOAuth2Scopes(permissions.BasePermission):
    """
    Custom permission to check auth scopes from Amsterdam schema.
    """

    def has_permission(self, request, view):
        """Tests whether a view can be requested."""
        if request.method == "OPTIONS":
            return True

        try:
            model = view.model
        except AttributeError:
            model = view.get_serializer_class().Meta.model

        if isinstance(view, ViewSetMixin) and view.action_map["get"] == "retrieve":
            # For detail views, consider the identifier to be part of the query parameters already.
            # This affects the mandatoryFilterSets matching on profile objects.
            request.user_scopes.add_query_params(view.table_schema.identifier)

        schema = model.table_schema()
        access = request.user_scopes.has_table_access(schema)
        log_access(request, access)
        return access

    def has_object_permission(self, request, view, obj):
        """Tests whether the view may access a particular object."""
        if request.method == "OPTIONS":
            return True

        # NOTE: For now, this is OK, later on we need to add row-level permissions.
        access = request.user_scopes.has_table_access(obj.table_schema())

        log_access(request, access)
        return access

    def has_permission_for_models(self, request, view, models):
        """Tests whether a set of models can be accessed.
        This variation doesn't exist in the standard DRF permission logic, but is used
        for the WFS/VMT views that reuse this permission class for checks.
        """
        if request.method == "OPTIONS":
            return True

        access = all(
            request.user_scopes.has_table_access(model.table_schema()) for model in models
        )

        log_access(request, access)
        return access


class CheckPermissionsMixin:
    """Mixin that adds a ``check_permissions()`` function to the view,
    which supports the DRF-plugins for permission checks on a non-DRF view (e.g. WFS/MVT).
    """

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [HasOAuth2Scopes]

    def check_permissions(self, request, models):
        """
        Check if the request should be permitted.
        """
        for permission in self.get_permissions():
            if not permission.has_permission_for_models(request, self, models):
                # Is Django's PermissionDenied so non-DRF views can handle this.
                raise PermissionDenied()

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]
