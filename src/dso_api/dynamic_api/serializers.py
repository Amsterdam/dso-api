from __future__ import annotations

from functools import lru_cache
from typing import Type

from django.db import models

from dso_api.lib.schematools.models import DynamicModel
from amsterdam_schema.types import DatasetTableSchema
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.serializers import DSOSerializer


class DynamicSerializer(DSOSerializer):
    """Base class for all generic serializers of this package."""

    table_schema: DatasetTableSchema = None

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


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param suffix: This can be "detail" or "list".
    """
    return f"dynamic_api:{model.get_dataset_id()}-{model.get_table_id()}-{suffix}"


@lru_cache()
def serializer_factory(model: Type[DynamicModel]) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model."""
    fields = ["_links"]
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
