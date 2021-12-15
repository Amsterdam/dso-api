import logging
from typing import cast

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from rest_framework import permissions
from rest_framework.viewsets import ViewSetMixin
from schematools.exceptions import SchemaObjectNotFound
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema

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


def validate_request(request, schema: DatasetTableSchema, allowed: set[str]) -> None:  # noqa: C901
    """Validate request method and parameters and check authorization for filters.

    The argument allowed is a set of parameters that are explicitly allowed.
    All other parameters are parsed as filters and rejected if not present in the schema.

    Raises FilterSyntaxError, SchemaObjectNotFound or PermissionDenied in case of a problem.
    """

    if request.method == "OPTIONS":
        return
    elif request.method != "GET":
        raise PermissionDenied(f"{request.method} request not allowed")

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
        mandatory.update(*profile.mandatory_filtersets)

    for key, values in request.GET.lists():
        if key in allowed:
            continue

        # Everything else is a filter.
        field_name, op = parse_filter(key)

        # mandatoryFilters may contain either the complete filter (with lookup operation)
        # or just the field name.
        if key in mandatory or field_name in mandatory:
            continue

        if schema.temporal is not None:
            if fields := schema.temporal.dimensions.get(field_name):
                for field in (fields.start, fields.end):
                    _check_filter(field, scopes, schema)
                continue

        _check_filter(field_name, scopes, schema)


def _check_filter(  # noqa: C901
    field_name: str, scopes: UserScopes, schema: DatasetTableSchema
) -> None:
    if field_name == "":
        raise ValueError("empty field name")

    while field_name != "":
        part, field_name, *_ = *field_name.split(".", 1), ""

        try:
            schema = schema.get_field_by_id(part)
        except SchemaObjectNotFound:
            # Relations with non-composite keys become a pseudo-property with the target table's
            # identifier appended to the table name: other_table_id. After camel-casing, that
            # becomes OtherTableId. The identifier can be anything, but here we don't have enough
            # information to cheaply determine what it was, so we assume it's "id", strip that off
            # and retry. Note that docs/source/datasets.py also assumes "Id", so any other
            # identifier already breaks the docs.
            #
            # TODO The dotted syntax for composite-key relations needs to be extended to this case.
            if part.endswith("Id"):
                part = part[: -len("Id")]
                field_name = part + ("." + field_name if field_name else "")
                continue

            raise

        # First check the field, then check whether it's a relation,
        # so we can "auth" to relations.
        if not scopes.has_field_access(schema):
            raise PermissionDenied(f"access denied to field {schema.id} with scopes {scopes}")

        if rel := schema.related_table:
            # scopes.has_field_access also checks table and dataset field.
            if not all(
                scopes.has_field_access(rel.get_field_by_id(ident)) for ident in rel.identifier
            ):
                raise PermissionDenied(f"access denied to field {schema.id} with scopes {scopes}")
            schema = rel


class FilterSyntaxError(Exception):
    """Signals a syntax error in a filter parameter."""

    pass


def parse_filter(v: str) -> tuple[str, str]:
    """Given a filter query parameter, returns the field name and operator.

    Does not validate the operator.

    E.g.,
        parse_filter("foo") == ("foo", "exact")
        parse_filter("foo[contains]") == ("foo", "contains")
    """
    bracket = v.find("[")
    if bracket == -1:
        if "]" in v:
            # Close bracket but no open bracket. Brackets don't occur in field names.
            raise FilterSyntaxError(f"missing open bracket ([) in {v!r}")
        field_name = v
        op = "exact"
    elif not v.endswith("]"):
        raise FilterSyntaxError(f"missing closing bracket (]) in {v!r}")
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
