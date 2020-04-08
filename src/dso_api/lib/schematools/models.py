from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Tuple, Type
from urllib.parse import urlparse

from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models.base import ModelBase
from django.conf import settings
from django_postgres_unlimited_varchar import UnlimitedCharField
from string_utils import slugify

from rest_framework_dso.crs import RD_NEW
from gisserver.types import CRS

from amsterdam_schema.types import (
    DatasetFieldSchema,
    DatasetSchema,
    DatasetTableSchema,
    field_is_nested_table
)

# Could be used to check fieldnames
ALLOWED_ID_PATTERN = re.compile(r"[a-zA-Z][ \w\d]*")

DATE_MODELS_LOOKUP = {
    "date": models.DateField,
    "time": models.TimeField,
    "date-time": models.DateTimeField,
}


TypeAndSignature = Tuple[Type[models.Field], tuple, Dict[str, Any]]


class FieldMaker:
    """Generate the field for a JSON-Schema property"""

    def __init__(
        self,
        field_cls: Type[models.Field],
        value_getter: Callable[[DatasetSchema], Dict[str, Any]] = None,
        **kwargs,
    ):
        self.field_cls = field_cls
        self.value_getter = value_getter
        self.kwargs = kwargs
        self.modifiers = [
            getattr(self, an) for an in dir(self) if an.startswith("handle_")
        ]

    def _make_related_classname(self, relation_urn):
        dataset_name, table_name = relation_urn.split(":")
        return f"{dataset_name}.{table_name.capitalize()}"

    def handle_basic(
        self,
        dataset: DatasetSchema,
        field: DatasetFieldSchema,
        field_cls,
        *args,
        **kwargs,
    ) -> TypeAndSignature:
        kwargs["primary_key"] = field.is_primary
        kwargs["null"] = not field.required
        if self.value_getter:
            kwargs = {**kwargs, **self.value_getter(dataset, field)}
        return field_cls, args, kwargs

    def handle_array(
        self,
        dataset: DatasetSchema,
        field: DatasetFieldSchema,
        field_cls,
        *args,
        **kwargs,
    ) -> TypeAndSignature:
        if field.data.get("type", "").lower() == "array":
            base_field, _ = JSON_TYPE_TO_DJANGO[
                field.data.get("entity", {}).get("type", "string")
            ]
            kwargs["base_field"] = base_field()
        return field_cls, args, kwargs

    def handle_relation(
        self,
        dataset: DatasetSchema,
        field: DatasetFieldSchema,
        field_cls,
        *args,
        **kwargs,
    ) -> TypeAndSignature:
        relation = field.relation

        if relation is not None:
            field_cls = models.ForeignKey
            args = [self._make_related_classname(relation), models.SET_NULL]
            # In schema foeign keys should be specified without _id,
            # but the db_column should be with _id
            if "parentTable" in field._parent_table["schema"]:
                kwargs["related_name"] = field._parent_table.id.replace(
                    field._parent_table["schema"]["parentTable"], "")[1:]
            kwargs["db_column"] = f"{slugify(field.name, sign='_')}_id"
            kwargs["db_constraint"] = False  # don't expect relations to exist.
        return field_cls, args, kwargs

    def handle_date(
        self,
        dataset: DatasetSchema,
        field: DatasetFieldSchema,
        field_cls,
        *args,
        **kwargs,
    ) -> TypeAndSignature:
        format_ = field.format
        if format_ is not None:
            field_cls = DATE_MODELS_LOOKUP[format_]
        return field_cls, args, kwargs

    def __call__(
        self, field: DatasetFieldSchema, dataset: DatasetSchema
    ) -> TypeAndSignature:
        field_cls = self.field_cls
        kwargs = self.kwargs
        args = []

        for modifier in self.modifiers:
            field_cls, args, kwargs = modifier(
                dataset, field, field_cls, *args, **kwargs
            )

        return field_cls, args, kwargs


def fetch_srid(dataset: DatasetSchema, field: DatasetFieldSchema) -> Dict[str, Any]:
    return {"srid": CRS.from_string(dataset.data["crs"]).srid}


JSON_TYPE_TO_DJANGO = {
    "string": (UnlimitedCharField, None),
    "integer": (models.IntegerField, None),
    "number": (models.FloatField, None),
    "boolean": (models.BooleanField, None),
    "date": (models.DateField, None),
    "time": (models.TimeField, None),
    "array": (ArrayField, None),
    "/definitions/id": (models.IntegerField, None),
    "/definitions/schema": (UnlimitedCharField, None),
    "https://geojson.org/schema/Geometry.json": (
        models.GeometryField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/Point.json": (
        models.PointField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/MultiPoint.json": (
        models.MultiPointField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/Polygon.json": (
        models.PolygonField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/MultiPolygon.json": (
        models.MultiPolygonField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/LineString.json": (
        models.LineStringField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/MultiLineString.json": (
        models.MultiLineStringField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
    "https://geojson.org/schema/GeometryCollection.json": (
        models.GeometryCollectionField,
        dict(
            value_getter=fetch_srid, srid=RD_NEW.srid, geography=False, db_index=True,
        ),
    ),
}


class DynamicModel(models.Model):
    """Base class to tag and detect dynamically generated models."""

    #: Overwritten by subclasses / factory
    _table_schema: DatasetTableSchema = None
    _display_field = None

    class Meta:
        abstract = True

    def __str__(self):
        if self._display_field:
            return getattr(self, self._display_field)
        else:
            return f"(no title: {self._meta.object_name} #{self.pk})"

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

    @classmethod
    def is_nested_table(cls):
        return cls._table_schema.get("schema", {}).get("parentTable") is not None


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
    module_name = f"dso_api.dynamic_api.{app_label}.models"
    model_name = f"{table.id.capitalize()}"

    # Generate fields
    fields = {}
    display_field = None
    for field in table.fields:
        type_ = field.type
        # skip schema field for now
        if type_.endswith("definitions/schema"):
            continue
        # skip nested tables
        if field_is_nested_table(field):
            continue
        # reduce amsterdam schema refs to their fragment
        if type_.startswith(settings.SCHEMA_DEFS_URL):
            type_ = urlparse(type_).fragment
        # Generate field object
        base_class, init_kwargs = JSON_TYPE_TO_DJANGO[type_]
        if base_class is None:
            # Some fields are not mapped into classes
            continue
        kls, args, kwargs = FieldMaker(base_class, **(init_kwargs or dict()))(
            field, dataset
        )
        if kls is None:
            # Some fields are not mapped into classes
            continue
        model_field = kls(*args, **kwargs)

        # Generate name, fix if needed.
        field_name = slugify(field.name, sign="_")
        model_field.name = field_name
        fields[field_name] = model_field

        if not display_field and is_possible_display_field(field):
            display_field = field.name

    # Generate Meta part
    meta_cls = type(
        "Meta",
        (),
        {
            "managed": False,
            "db_table": get_db_table_name(table),
            "app_label": app_label,
            "verbose_name": table.id.title(),
            "ordering": ("id",),
        },
    )

    # Generate the model
    return ModelBase(
        model_name,
        (DynamicModel,),
        {
            **fields,
            "_dataset_schema": dataset,
            "_table_schema": table,
            "_display_field": "",
            "__module__": module_name,
            "Meta": meta_cls,
        },
    )


def is_possible_display_field(field: DatasetFieldSchema) -> bool:
    """See whether the field is a possible candidate as display field"""
    # TODO: the schema needs to provide a display field!
    return (
        field.type == "string"
        and "$ref" not in field
        and " " not in field.name
        and not field.name.endswith("_id")
    )


def get_db_table_name(table: DatasetTableSchema) -> str:
    """Generate the table name for a database schema."""
    dataset = table._parent_schema
    app_label = dataset.id
    table_id = table.id
    return slugify(f"{app_label}_{table_id}", sign="_")
