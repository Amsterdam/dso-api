from typing import Dict, Iterable, Union

from django.db import models
from rest_framework import serializers
from rest_framework.exceptions import ParseError, PermissionDenied

from rest_framework_dso.fields import AbstractEmbeddedField
from dso_api.dynamic_api.permissions import fetch_scopes_for_model

EmbeddedFieldDict = Dict[str, AbstractEmbeddedField]


class EmbeddedHelper:
    def __init__(
        self, parent_serializer: serializers.ModelSerializer, expand: Union[list, bool],
    ):
        """Find all serializers that are configured for the sideloading feature.

        This returns a dictionary with the all serializer classes.
        The dictionary only contains the items for which sideloading is requested.
        """
        self.parent_serializer = parent_serializer
        self.embedded_fields = self._get_embedded_fields(expand) if expand else {}

    def _get_embedded_fields(self, expand: Union[list, bool]):  # noqa: C901
        allowed_names = getattr(self.parent_serializer.Meta, "embedded_fields", [])
        auth_checker = getattr(
            self.parent_serializer, "get_auth_checker", lambda: None
        )()
        embedded_fields = {}

        # ?expand=true should expand all names
        if expand is True:
            expand = allowed_names
            specified_expands = set()
        else:
            specified_expands = set(expand)

        for field_name in expand:
            if field_name not in allowed_names:
                available = ", ".join(sorted(allowed_names))
                if not available:
                    raise ParseError(
                        "Eager loading is not supported for this endpoint"
                    ) from None
                else:
                    raise ParseError(
                        f"Eager loading is not supported for field '{field_name}', "
                        f"available options are: {available}"
                    ) from None

            # Get the field, and
            try:
                field = getattr(self.parent_serializer, field_name)
                scopes = fetch_scopes_for_model(field.related_model)
                if auth_checker and not auth_checker(*scopes.table):
                    if field_name in specified_expands:
                        raise PermissionDenied(
                            f"Eager loading not allowed for field '{field_name}'"
                        )
                    continue
                embedded_fields[field_name] = field
            except AttributeError:
                raise RuntimeError(
                    f"{self.parent_serializer.__class__.__name__}.{field_name}"
                    f" does not refer to an embedded field."
                ) from None

        # Add authorization check
        return embedded_fields

    def get_list_embedded(self, instances: Iterable[models.Model]):
        """Expand the embedded models for a list serializer.

        This collects which objects to query, and returns those in a group per field,
        which can be used in the ``_embedded`` section.
        """
        ids_per_relation = {}
        ids_per_model = {}
        for name, embedded_field in self.embedded_fields.items():
            related_model = embedded_field.related_model
            object_ids = embedded_field.get_related_ids(instances)

            # Collect all ID's to fetch
            ids_per_relation[name] = object_ids
            ids_per_model.setdefault(related_model, set()).update(object_ids)

        # Fetch model data
        fetched_per_model = {
            model: model.objects.in_bulk(ids) for model, ids in ids_per_model.items()
        }
        _embedded = {}
        for name, embedded_field in self.embedded_fields.items():
            related_model = embedded_field.related_model
            data = fetched_per_model[related_model]

            embedded_serializer = embedded_field.get_serializer(
                parent=self.parent_serializer
            )
            _embedded[name] = [
                embedded_serializer.to_representation(data[id])
                for id in ids_per_relation[name]
            ]

        return _embedded

    def get_embedded(self, instance: models.Model) -> dict:
        """Expand the embedded models for a regular (detail) serializer.

        The returned dictionary can be used in the ``_embedded`` section.
        """
        # Resolve all embedded elements
        ret = {}
        for name, embedded_field in self.embedded_fields.items():
            # Note: this currently assumes a detail view only references other models once:
            id_value = embedded_field.get_related_id(instance)
            if id_value is None:
                # Unclear in HAL-JSON: should the requested embed be mentioned or not?
                ret[name] = None
                continue

            related_model = embedded_field.related_model
            try:
                value = related_model.objects.get(pk=id_value)
            except related_model.DoesNotExist:
                # Unclear in HAL-JSON: should the requested embed be mentioned or not?
                ret[name] = None
                continue

            embedded_serializer = embedded_field.get_serializer(
                parent=self.parent_serializer
            )
            ret[name] = embedded_serializer.to_representation(value)
        return ret
