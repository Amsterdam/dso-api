import logging
from typing import cast

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from rest_framework import permissions
from rest_framework.viewsets import ViewSetMixin
from schematools.exceptions import SchemaObjectNotFound
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema, Permission

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


def filter_unauthorized_expands(
    user_scopes: UserScopes, expanded_fields: list[EmbeddedFieldMatch], skip_unauth=False
) -> list[EmbeddedFieldMatch]:
    """Remove expanded fields if these are not accessible"""

    result = []
    for match in expanded_fields:
        field_perm = user_scopes.has_field_access(match.field.field_schema)
        table_perm = user_scopes.has_table_access(match.field.related_model.table_schema())
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
        if access and not self._filters_ok(request, schema):
            # Don't give access when the user is filtering on fields they may not see.
            access = Permission.none

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

    def _filters_ok(self, request, schema: DatasetTableSchema) -> bool:  # noqa: C901
        """Check field authorization for requested filters."""

        # Workaround for BBGA, which has a broken schema and is queried in a funny way
        # by another application.
        if schema.dataset.id == "bbga":
            return True

        # Type hack: DRF requests have a __getattr__ that delegates to an HttpRequest.
        request = cast(HttpRequest, request)

        # And then we and authorization_django monkey-patch the scopes onto the request.
        scopes = cast(UserScopes, request.user_scopes)

        # Collect mandatory filters. We need to make an exception for these to handle cases
        # where the field they reference isn't otherwise accessible.
        # The actual check for whether the filter sets are provided lives elsewhere.
        mandatory = set()
        for profile in scopes.get_active_profile_tables(schema.dataset.id, schema.id):
            for f in profile.mandatory_filtersets:
                mandatory.update(f)

        for key, values in request.GET.lists():
            if key in ("fields", "format", "page", "page_size", "sorteer") or key.startswith("_"):
                continue

            # Everything else is a filter.
            field_name, op = _parse_filter(key)

            # mandatoryFilters may contain either the complete filter (with lookup operation)
            # or just the field name.
            if key in mandatory or field_name in mandatory:
                continue

            if schema.temporal is not None:
                if fields := schema.temporal.dimensions.get(field_name):
                    if any(
                        not self._filter_ok(field, scopes, schema)
                        for field in (fields.start, fields.end)
                    ):
                        return False
                    else:
                        continue

            if not self._filter_ok(field_name, scopes, schema):
                return False

        return True

    def _filter_ok(self, field_name: str, scopes: UserScopes, schema: DatasetTableSchema) -> bool:
        schema_part = schema
        parts = field_name.split(".")  # Handle subfields.
        for i, part in enumerate(parts):
            try:
                schema_part = schema_part.get_field_by_id(part)
            except SchemaObjectNotFound as e:
                # TODO: this should be a ValidationError,
                # but that exception isn't handled properly from here.
                # Raise PermissionDenied to at least get the exception message to the client.
                raise PermissionDenied(f"{field_name} not found in schema") from e
            if not scopes.has_field_access(schema_part):
                return False

        return True


def _parse_filter(v: str) -> tuple[str, str]:
    """Given a filter query parameter, returns the field name and operator.

    Does not validate the operator.

    E.g.,
        parse_filter("foo") == ("foo", "exact")
        parse_filter("foo[contains]") == ("foo", "contains")
    """
    bracket = v.find("[")
    if bracket == -1:
        field_name = v
        op = "exact"
    elif not v.endswith("]"):
        raise ValueError(f"missing closing bracket (]) in {v!r}")
    else:
        field_name = v[:bracket]
        op = v[bracket + 1 : -1]

    return field_name, op


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
