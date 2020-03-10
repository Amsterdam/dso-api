from __future__ import annotations

import re
from functools import lru_cache
from typing import Type
from collections import OrderedDict

from django.db import models

from dso_api.lib.schematools.models import DynamicModel
from amsterdam_schema.types import DatasetTableSchema
from rest_framework import serializers
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.serializers import DSOSerializer
from dso_api.dynamic_api.permissions import fetch_scopes_for_model


class _DynamicLinksField(DSOSerializer.serializer_url_field):
    def to_representation(self, value: DynamicModel):
        """Before generating the URL, check whether the "PK" value is valid.
        This avoids more obscure error messages when the string.
        """
        pk = value.pk
        if pk and not isinstance(pk, int):
            viewset = self.root.context.get("view")
            if viewset is not None:  # testing serializer without view
                lookup = getattr(viewset, "lookup_value_regex", "[^/.]+")
                if not re.fullmatch(lookup, value.pk):
                    raise RuntimeError(
                        "Unsupported URL characters in "
                        f"{value.get_dataset_id()}/{value.get_table_id()} id='{value.pk}' "
                    )
        return super().to_representation(value)


class DynamicSerializer(DSOSerializer):
    """Base class for all generic serializers of this package."""

    serializer_url_field = _DynamicLinksField

    schema = serializers.SerializerMethodField()

    table_schema: DatasetTableSchema = None

    def get_auth_checker(self):
        request = self.context.get("request")
        return getattr(request, "is_authorized_for", None) if request else None

    def get_schema(self, instance):
        """The schema field is exposed with every record"""
        name = instance.get_dataset_id()
        table = instance.get_table_id()
        return f"https://schemas.data.amsterdam.nl/datasets/{name}/{name}#{table}"

    def build_url_field(self, field_name, model_class):
        """Make sure the generated URLs point to our dynamic models"""
        field_class = self.serializer_url_field
        field_kwargs = {
            "view_name": get_view_name(model_class, "detail"),
        }

        return field_class, field_kwargs

    def build_relational_field(self, field_name, relation_info):
        field_class, field_kwargs = super().build_relational_field(
            field_name, relation_info
        )
        if "view_name" in field_kwargs:
            model_class = relation_info[1]
            field_kwargs["view_name"] = get_view_name(model_class, "detail")

        return field_class, field_kwargs

    def get_unauthorized_fields(self) -> set:
        model = self.Meta.model
        request = self.context.get("request")
        scopes_info = fetch_scopes_for_model(model)
        all_fields = set([f.name for f in model._meta.get_fields()])
        unauthorized_fields = set()
        if hasattr(request, "is_authorized_for"):
            for name in all_fields:
                scopes = scopes_info["field"].get(name)
                if scopes is None:
                    continue
                if not request.is_authorized_for(*scopes):
                    unauthorized_fields.add(name)
        if unauthorized_fields:
            return unauthorized_fields

        return set()

    def to_representation(self, instance):
        unauthorized_fields = self.get_unauthorized_fields()

        if unauthorized_fields:
            # Limit result to allowed fields only
            self.fields = OrderedDict(
                [
                    (field_name, field)
                    for field_name, field in self.fields.items()
                    if field_name not in unauthorized_fields
                ]
            )
        return super().to_representation(instance)


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param suffix: This can be "detail" or "list".
    """
    return f"dynamic_api:{model.get_dataset_id()}-{model.get_table_id()}-{suffix}"


@lru_cache()
def serializer_factory(model: Type[DynamicModel]) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model."""
    fields = ["_links", "schema"]
    serializer_name = f"{model.get_dataset_id()}{model.__name__}Serializer"
    new_attrs = {
        "table_schema": model._table_schema,
        "__module__": f"dso_api.dynamic_api.serializers.{model.get_dataset_id()}",
    }

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        if isinstance(model_field, models.ForeignKey):
            new_attrs[model_field.name] = EmbeddedField(
                serializer_class=serializer_factory(model_field.related_model),
            )
            fields.append(model_field.attname)

        fields.append(model_field.name)

    # Generate Meta section and serializer class
    new_attrs["Meta"] = type("Meta", (), {"model": model, "fields": fields})
    return type(serializer_name, (DynamicSerializer,), new_attrs)
