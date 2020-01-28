from __future__ import annotations

import re
from typing import List, Type, Tuple, Dict, Any, Callable
from string_utils import slugify

from django.contrib.gis.db import models
from django.db.models.base import ModelBase
from django_postgres_unlimited_varchar import UnlimitedCharField
from schematools.schema.types import (
    DatasetTableSchema,
    DatasetSchema,
    DatasetFieldSchema,
)


# Could be used to check fieldnames
ALLOWED_ID_PATTERN = re.compile(r"[a-zA-Z][ \w\d]*")


def _make_related_classname(relation_urn):
    dataset_name, table_name = relation_urn.split(":")
    return f"{dataset_name}.{table_name.capitalize()}"


def field_model_factory(
    field_model,
    value_getter: Callable[[DatasetSchema], Dict[str, Any]] = None,
    **kwargs,
) -> Callable:
    def fetch_field_model(
        field: DatasetFieldSchema, dataset: DatasetSchema,
    ) -> Tuple[Type[models.Model], Dict[str, Any]]:
        kw = kwargs.copy()
        final_field_model = field_model
        args = []
        kw["primary_key"] = field.is_primary
        kw["null"] = not field.required
        relation = field.relation
        if relation is not None:
            final_field_model = models.ForeignKey
            args = [_make_related_classname(relation), models.SET_NULL]
            kw["db_column"] = f"{slugify(field.name, sign='_')}"
        if value_getter:
            kw = {**kw, **value_getter(dataset)}
        return (final_field_model, args, kw)

    return fetch_field_model


def fetch_crs(dataset: DatasetSchema) -> Dict[str, Any]:
    return {"srid": int(dataset.data["crs"].split("EPSG:")[1])}


JSON_TYPE_TO_DJANGO = {
    "string": field_model_factory(UnlimitedCharField),
    "integer": field_model_factory(models.IntegerField),
    "number": field_model_factory(models.FloatField),
    "boolean": field_model_factory(models.BooleanField),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/id": field_model_factory(
        models.IntegerField
    ),
    "https://schemas.data.amsterdam.nl/schema@v1.1.0#/definitions/schema": field_model_factory(
        UnlimitedCharField
    ),
    "https://geojson.org/schema/Geometry.json": field_model_factory(
        models.MultiPolygonField, value_getter=fetch_crs, srid=28992, geography=False
    ),
    "https://geojson.org/schema/Point.json": field_model_factory(
        models.PointField, value_getter=fetch_crs, srid=28992, geography=False
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


def schema_models_factory(
    dataset: DatasetSchema, tables=None
) -> List[Type[DynamicModel]]:
    """Generate Django models from the data of the schema."""
    return [
        model_factory(table)
        for table in dataset.tables
        if tables is None or table.id in tables
    ]


def model_factory(table: DatasetTableSchema) -> Type[DynamicModel]:
    """Generate a Django model class from a JSON Schema definition."""
    dataset = table._parent_schema
    app_label = dataset.id
    module_name =  f"schematools.schema.{app_label}.models"
    model_name = f"{table.id.capitalize()}"

    # Generate fields
    fields = {}
    for field in table.fields:
        kls, args, kwargs = JSON_TYPE_TO_DJANGO[field.type](field, dataset)
        fields[slugify(field.name, sign="_")] = kls(*args, **kwargs)

    # Generate Meta part
    meta_cls = type(
        "Meta",
        (),
        {
            "managed": False,
            "db_table": f"{app_label}_{table.id}",
            "app_label": app_label,
            "verbose_name": table.id,
        },
    )

    # Generate the model
    return ModelBase(
        model_name,
        (DynamicModel,),
        {
            **fields,
            "_table_schema": table,
            "__module__": module_name,
            "Meta": meta_cls,
        },
    )
