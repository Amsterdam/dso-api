from __future__ import annotations

from typing import List, Type

from django.contrib.gis.db import models
from django.db.models.base import ModelBase
from django_postgres_unlimited_varchar import UnlimitedCharField
from schematools.schema.types import DatasetTableSchema, DatasetSchema

JSON_TYPE_TO_DJANGO = {
    "string": (UnlimitedCharField, {}),
    "integer": (models.IntegerField, {}),
    "number": (models.FloatField, {}),
    "boolean": (models.BooleanField, {}),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/id": (
        models.IntegerField,
        {},
    ),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/schema": (
        UnlimitedCharField,
        {},
    ),
    "https://geojson.org/schema/Geometry.json": (
        models.MultiPolygonField,
        {"srid": 28992, "geography": False},
    ),
    "https://geojson.org/schema/Point.json": (
        models.PointField,
        {"srid": 28992, "geography": False},
    ),
}


class DynamicModel(models.Model):
    """Base class to tag and detect dynamically generated models."""

    #: Overwritten by subclasses / factory
    _table_schema: DatasetTableSchema = None

    class Meta:
        abstract = True

    # These classmethods could have been a 'classproperty',
    # but this ensures the names don't conflict with fields from the schema.

    @classmethod
    def get_dataset(cls) -> DatasetSchema:
        """Give access to the original dataset that this model is a part of."""
        return cls._table_schema._parent_schema

    @classmethod
    def get_dataset_id(cls) -> str:
        return cls._table_schema._parent_schema.id

    @classmethod
    def get_table_id(cls) -> str:
        """Give access to the table name"""
        return cls._table_schema.id


def schema_models_factory(dataset: DatasetSchema, tables=None) -> List[Type[DynamicModel]]:
    """Generate Django models from the data of the schema."""
    return [
        model_factory(table)
        for table in dataset.tables
        if tables is None or table.id in tables
    ]


def model_factory(table: DatasetTableSchema) -> Type[DynamicModel]:
    """Generate a Django model class from a JSON Schema definition."""
    app_label = table._parent_schema.id
    fields = {}
    for field in table.fields:
        kls, kw = JSON_TYPE_TO_DJANGO[field.type]
        if field.is_primary:
            kw["primary_key"] = True
        fields[field.name] = kls(**kw)

    model_name = f"{table.id.capitalize()}"

    meta_cls = type("Meta", (), {
        "managed": False,
        "db_table": f"{app_label}_{table.id}",
        "app_label": app_label,
    })

    return ModelBase(model_name, (DynamicModel,), {
        **fields,
        "_table_schema": table,
        "__module__": f"schematools.schema.{app_label}.models",
        "Meta": meta_cls
    })
