from __future__ import annotations

from functools import lru_cache
from typing import Type

from dso_api.lib.schematools.models import DynamicModel
from dso_api.lib.schematools.types import DatasetTableSchema
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
    # Generate serializer "Meta" attribute
    fields = ["_links"] + [x.name for x in model._meta.get_fields()]
    new_meta_attrs = {"model": model, "fields": fields}

    # Generate serializer class
    serializer_name = f"{model.__name__}Serializer"
    new_attrs = {
        "table_schema": model._table_schema,
        "__module__": "various_small_datasets.gen_api.serializers",
        "Meta": type("Meta", (), new_meta_attrs),
    }
    return type(serializer_name, (DynamicSerializer,), new_attrs)
