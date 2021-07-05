"""The serializer logic extends from the
:class:`~rest_framework_dso.serializer.DSOSerializer`
and not :class:`~rest_framework_dso.serializer.DSOModelSerializer`.
The serializers mainly make sure the response is outputted in a DSO-compatible format.
"""
from typing import Dict, List
from urllib.parse import urlparse

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from schematools.contrib.django.models import Dataset
from schematools.types import DatasetFieldSchema, DatasetTableSchema
from schematools.utils import to_snake_case, toCamelCase

from rest_framework_dso.fields import DSOGeometryField
from rest_framework_dso.serializers import DSOListSerializer, DSOSerializer

JSON_TYPE_TO_DRF = {
    "string": serializers.CharField,
    "integer": serializers.IntegerField,
    "number": serializers.FloatField,
    "boolean": serializers.BooleanField,
    "array": serializers.ListField,
    "/definitions/id": serializers.IntegerField,
    "https://geojson.org/schema/Geometry.json": DSOGeometryField,
    "https://geojson.org/schema/Point.json": DSOGeometryField,
    "https://geojson.org/schema/MultiPoint.json": DSOGeometryField,
    "https://geojson.org/schema/Polygon.json": DSOGeometryField,
    "https://geojson.org/schema/MultiPolygon.json": DSOGeometryField,
    "https://geojson.org/schema/LineString.json": DSOGeometryField,
    "https://geojson.org/schema/MultiLineString.json": DSOGeometryField,
    "https://geojson.org/schema/GeometryCollection.json": DSOGeometryField,
}


class RemoteListSerializer(DSOListSerializer):
    """ListSerializer that takes remote data.

    This is automatically used when ``many=True``
    is used on :class:`RemoteSerializer` construction.
    """

    @property
    def expanded_fields(self):
        return []


class RemoteSerializer(DSOSerializer):
    """Serializer that takes remote data"""

    table_schema = None  # defined by factory
    schema = serializers.SerializerMethodField()

    _default_list_serializer_class = RemoteListSerializer

    @extend_schema_field(OpenApiTypes.URI)
    def get_schema(self, instance):
        """The schema field is exposed with every record"""
        name = self.table_schema._parent_schema.id
        table = self.table_schema.id
        dataset_path = Dataset.objects.get(name=name).path
        return f"https://schemas.data.amsterdam.nl/datasets/{dataset_path}/dataset#{table}"


class RemoteObjectSerializer(DSOSerializer):
    table_schema = None  # defined by factory
    field_schema = None  # defined by factory


def remote_serializer_factory(table_schema: DatasetTableSchema):
    """Generate the DRF serializer class for a specific dataset model."""
    dataset = table_schema._parent_schema
    serializer_name = (f"{dataset.id.title()}{table_schema.id.title()}Serializer").replace(
        " ", "_"
    )
    new_attrs = {
        "table_schema": table_schema,
        "__module__": f"dso_api.dynamic_api.remote.serializers.{dataset.id}",
    }

    declared_fields = _build_declared_fields(table_schema.fields)

    # Generate Meta section and serializer class
    new_attrs.update(declared_fields)
    new_attrs["Meta"] = type(
        "Meta",
        (),
        {
            "fields": list(declared_fields.keys()),
            "many_results_field": table_schema.id.title(),
        },
    )
    return type(serializer_name, (RemoteSerializer,), new_attrs)


def _build_declared_fields(
    fields: List[DatasetFieldSchema],
) -> Dict[str, serializers.Field]:
    """Generate the serializer fields for a list of fields."""
    # Parse fields for serializer
    declared_fields = {}
    for field in fields:
        # In case metadata fields are mentioned in the schema, ignore these.
        if field.type.endswith("definitions/schema") or field.name == "_links":
            continue

        # Instead of having to apply camelize() on every response,
        # create converted field names on the serializer construction.
        # The space replacement is unlikely for a remote field, but kept for consistency.
        safe_field_name = field.name.replace(" ", "_")
        camel_name = toCamelCase(safe_field_name)

        kwargs = {"required": field.required, "allow_null": not field.required}
        if field.type == "string" and not field.required:
            kwargs["allow_blank"] = True
        if camel_name != field.name:
            kwargs["source"] = field.name
        declared_fields[camel_name] = _remote_field_factory(field, **kwargs)

    return declared_fields


def _remote_field_factory(field: DatasetFieldSchema, **kwargs) -> serializers.Field:
    """Generate the serializer field for a single schema field."""
    type_ = field.type
    # reduce amsterdam schema refs to their fragment
    if type_.startswith(settings.SCHEMA_DEFS_URL):
        type_ = urlparse(type_).fragment

    if type_ == "object":
        # Generate a serializer class for the object
        return _remote_object_field_factory(field, **kwargs)
    else:
        if type_ == "array":
            if field["items"]["type"] == "object":
                kwargs["child"] = _remote_object_field_factory(field, **kwargs)
            else:
                kwargs["child"] = JSON_TYPE_TO_DRF[field["items"]["type"]](**kwargs)
        field_cls = JSON_TYPE_TO_DRF[type_]
        return field_cls(**kwargs)


def _remote_object_field_factory(field: DatasetFieldSchema, **kwargs) -> RemoteObjectSerializer:
    """Generate a serializer for an sub-object field"""
    table_schema = field.table
    dataset = table_schema.dataset
    safe_dataset_id = to_snake_case(dataset.id)
    serializer_name = (
        f"{dataset.id.title()}{table_schema.id.title()}_{field.name.title()}Serializer"
    ).replace(" ", "_")
    new_attrs = {
        "table_schema": table_schema,
        "field_schema": field,
        "__module__": f"dso_api.dynamic_api.remote.serializers.{safe_dataset_id}",
    }

    declared_fields = _build_declared_fields(field.sub_fields)

    # Generate Meta section and serializer class
    new_attrs.update(declared_fields)
    new_attrs["Meta"] = type("Meta", (), {"fields": list(declared_fields.keys())})
    serializer_class = type(serializer_name, (RemoteObjectSerializer,), new_attrs)
    return serializer_class(**kwargs)
