from typing import Dict, Iterable, Union

from django.db import models
from rest_framework import serializers
from rest_framework.exceptions import ParseError, PermissionDenied

from rest_framework_dso.fields import AbstractEmbeddedField
from dso_api.dynamic_api.permissions import fetch_scopes_for_model

EmbeddedFieldDict = Dict[str, AbstractEmbeddedField]


class EmbeddedHelper:
    def __init__(
        self,
        parent_serializer: serializers.ModelSerializer,
        expand: Union[list, bool],
    ):
        """Find all serializers that are configured for the sideloading feature.

        This returns a dictionary with the serializer classes.
        The dictionary only contains the items for which sideloading is requested.
        """
        self.parent_serializer = parent_serializer
        self.embedded_fields = self._get_embedded_fields(expand) if expand else {}

        self.id_based_fetcher = (
            parent_serializer.id_based_fetcher or self._default_id_based_fetcher
        )

    def _default_id_based_fetcher(self, model, is_loose=False):
        """Default behaviour to fetch objects based on a set of ids is to use
        Django's in_bulk manager method. This can be overridden by setting
        a fetcher function on the parent_serializer. Doing it this way, we
        do not pollute the rest_framework_dso package with too specific behaviour
        """
        assert (
            not is_loose
        ), "Default in_bulk fetcher should not be used on loose relations"
        return model.objects.in_bulk

    def _get_embedded_fields(self, expand: Union[list, bool]):  # noqa: C901
        allowed_names = getattr(self.parent_serializer.Meta, "embedded_fields", [])
        auth_checker = getattr(
            self.parent_serializer, "get_auth_checker", lambda: None
        )()
        embedded_fields = {}

        # ?_expand=true should expand all names
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
            except AttributeError:
                raise RuntimeError(
                    f"{self.parent_serializer.__class__.__name__}.{field_name}"
                    f" does not refer to an embedded field."
                ) from None
            else:
                scopes = fetch_scopes_for_model(field.related_model)
                if auth_checker and not auth_checker(*scopes.table):
                    if field_name in specified_expands:
                        raise PermissionDenied(
                            f"Eager loading not allowed for field '{field_name}'"
                        )
                    continue
                embedded_fields[field_name] = field

        # Add authorization check
        return embedded_fields

    def get_list_embedded(self, instances: Iterable[models.Model]):
        """Expand the embedded models for a list serializer.

        This collects which objects to query, and returns those in a group per field,
        which can be used in the ``_embedded`` section.
        """
        ids_per_relation = {}
        ids_per_model = {}
        loose_models = set()
        for name, embedded_field in self.embedded_fields.items():
            related_model = embedded_field.related_model
            object_ids = embedded_field.get_related_list_ids(instances)
            if embedded_field.is_loose:
                loose_models.add(related_model)

            # Collect all ID's to fetch
            ids_per_relation[name] = object_ids
            ids_per_model.setdefault(related_model, set()).update(object_ids)

        # Fetch model data
        fetched_per_model = {
            model: self.id_based_fetcher(model, is_loose=model in loose_models)(ids)
            for model, ids in ids_per_model.items()
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
                if id in data
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
            id_values = embedded_field.get_related_detail_ids(instance)
            if not id_values:
                # Unclear in HAL-JSON: should the requested embed be mentioned or not?
                ret[name] = None
                continue

            related_model = embedded_field.related_model
            try:
                values = [
                    self.id_based_fetcher(
                        related_model, is_loose=embedded_field.is_loose
                    )([id_value])[id_value]
                    for id_value in id_values
                ]
            except KeyError:
                # Unclear in HAL-JSON: should the requested embed be mentioned or not?
                ret[name] = None
                continue

            embedded_serializer = embedded_field.get_serializer(
                parent=self.parent_serializer
            )
            serialized = [
                embedded_serializer.to_representation(value) for value in values
            ]
            # When we have a one-size list, we unpack it
            ret[name] = serialized if len(serialized) > 1 else serialized[0]
        return ret
