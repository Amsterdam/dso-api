from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Tuple, Type

from django.contrib.gis.db import models
from django.db.models.base import ModelBase
from django_postgres_unlimited_varchar import UnlimitedCharField
from string_utils import slugify

from amsterdam_schema.types import DatasetFieldSchema, DatasetSchema, DatasetTableSchema

# Could be used to check fieldnames
ALLOWED_ID_PATTERN = re.compile(r"[a-zA-Z][ \w\d]*")

DATE_MODELS_LOOKUP = {"date": models.DateField, "date-time": models.DateTimeField}


TypeAndSignature = Tuple[Type[models.Field], List[Any], Dict[str, Any]]


class FieldMaker:
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
        self, field: DatasetFieldSchema, field_cls, *args, **kwargs
    ) -> TypeAndSignature:
        kwargs["primary_key"] = field.is_primary
        kwargs["null"] = not field.required
        return field_cls, args, kwargs

    def handle_relation(
        self, field: DatasetFieldSchema, field_cls, *args, **kwargs
    ) -> TypeAndSignature:
        relation = field.relation

        if relation is not None:
            field_cls = models.ForeignKey
            args = [self._make_related_classname(relation), models.SET_NULL]
            kwargs["db_column"] = f"{slugify(field.name, sign='_')}"
            kwargs["db_constraint"] = False  # don't expect relations to exist.
        return field_cls, args, kwargs

    def handle_date(
        self, field: DatasetFieldSchema, field_cls, *args, **kwargs
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
            field_cls, args, kwargs = modifier(field, field_cls, *args, **kwargs)

        return field_cls, args, kwargs


def field_model_factory(
    field_cls: Type[models.Field],
    value_getter: Callable[[DatasetSchema], Dict[str, Any]] = None,
    **kwargs,
) -> Callable:
    """Generate the field for a JSON-Schema property"""

    return FieldMaker(field_cls, value_getter, **kwargs)


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
        # Generate field object
        kls, args, kwargs = JSON_TYPE_TO_DJANGO[field.type](field, dataset)
        model_field = kls(*args, **kwargs)

        # Generate name, fix if needed.
        field_name = slugify(field.name, sign="_")
        if isinstance(model_field, models.ForeignKey) and field_name.endswith("_id"):
            field_name = field_name[:-3]
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
        },
    )

    # Generate the model
    return ModelBase(
        model_name,
        (DynamicModel,),
        {
            **fields,
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
    return f"{app_label}_{table.id}"
