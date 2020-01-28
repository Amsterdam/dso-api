from __future__ import annotations

from functools import lru_cache
from typing import Type

from dso_api.dynamic_api.models import DynamicModel
from dso_api.datasets.types import DatasetTableSchema

from rest_framework_dso.serializers import DSOSerializer


class DynamicSerializer(DSOSerializer):
    """Base class for all generic serializers of this package."""
    table_schema: DatasetTableSchema = None


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
