from __future__ import annotations

import re
from collections import OrderedDict
from functools import lru_cache
from string_utils import slugify
from typing import Type

from django.db import models

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.serializers import DSOModelSerializer
from schematools.types import DatasetTableSchema
from schematools.contrib.django.models import DynamicModel

from dso_api.dynamic_api.permissions import get_unauthorized_fields
from dso_api.dynamic_api.utils import snake_to_camel_case, format_field_name


class _DynamicLinksField(DSOModelSerializer.serializer_url_field):
    def to_representation(self, value: DynamicModel):
        """Before generating the URL, check whether the "PK" value is valid.
        This avoids more obscure error messages when the string.
        """
        pk = value.pk
        if pk and not isinstance(pk, int):
            viewset = self.root.context.get("view")
            if viewset is not None:  # testing serializer without view
                lookup = getattr(viewset, "lookup_value_regex", "[^/.]+")
                if not re.fullmatch(lookup, pk):
                    full_table_id = f"{value.get_dataset_id()}.{value.get_table_id()}"
                    raise RuntimeError(
                        "Unsupported URL characters in object ID of model "
                        f"{full_table_id}: instance id={pk}"
                    )
        return super().to_representation(value)


class DynamicSerializer(DSOModelSerializer):
    """Base class for all generic serializers of this package."""

    serializer_url_field = _DynamicLinksField

    schema = serializers.SerializerMethodField()

    table_schema: DatasetTableSchema = None

    def get_request(self):
        """
        Get request from this or parent instance.
        """
        return self.context["request"]

    @property
    def fields(self):
        fields = super().fields
        request = self.get_request()

        # Adjust the serializer based on the request.
        # request can be None for get_schema_view(public=True)
        if request is not None:
            unauthorized_fields = get_unauthorized_fields(request, self.Meta.model)
            if unauthorized_fields:
                fields = OrderedDict(
                    [
                        (field_name, field)
                        for field_name, field in fields.items()
                        if field_name not in unauthorized_fields
                    ]
                )
        return fields

    def get_auth_checker(self):
        request = self.get_request()
        return getattr(request, "is_authorized_for", None) if request else None

    @extend_schema_field(OpenApiTypes.URI)
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


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param suffix: This can be "detail" or "list".
    """
    dataset_id = slugify(model.get_dataset_id(), separator="_")
    table_id = slugify(model.get_table_id(), separator="_")
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


@lru_cache()
def serializer_factory(
    model: Type[DynamicModel], seen: frozenset, flat=None
) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model."""
    fields = ["_links", "schema"]
    if model.has_parent_table():
        # Inner tables have no schema or links defined.
        fields = []

    safe_dataset_id = slugify(model.get_dataset_id(), separator="_")
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}Serializer"
    new_attrs = {
        "table_schema": model._table_schema,
        "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
    }

    # Parse fields for serializer
    extra_kwargs = {"seen": seen}
    for model_field in model._meta.get_fields():
        generate_field_serializer(model, model_field, new_attrs, fields, extra_kwargs)

    # Generate embedded relations
    if not flat:
        generate_embedded_relations(model, fields, new_attrs)

    # Generate Meta section and serializer class
    new_attrs["Meta"] = type(
        "Meta", (), {"model": model, "fields": fields, "extra_kwargs": extra_kwargs}
    )
    return type(serializer_name, (DynamicSerializer,), new_attrs)


def generate_field_serializer(model, model_field, new_attrs, fields, extra_kwargs):
    orig_name = model_field.name
    # Instead of having to apply camelize() on every response,
    # create converted field names on the serializer construction.
    camel_name = snake_to_camel_case(model_field.name)
    seen = extra_kwargs.get("seen", frozenset())
    if isinstance(model_field, models.ManyToOneRel):
        if camel_name not in seen and camel_name == "buurt":
            new_seen = set(seen)
            new_seen.add(camel_name)
            new_attrs[camel_name] = EmbeddedField(
                serializer_class=serializer_factory(
                    model_field.related_model, frozenset(new_seen), flat=True
                ),
                source=model_field.name,
            )
            fields.append(camel_name)
            extra_kwargs[camel_name] = {"source": model_field.name + "_set"}
        return
    if model.has_parent_table() and model_field.name in ["id", "parent"]:
        # Do not render PK and FK to parent on nested tables
        return

    # Add extra embedded part for foreign keys
    if isinstance(model_field, models.ForeignKey):
        if camel_name not in seen:
            new_attrs[camel_name] = EmbeddedField(
                serializer_class=serializer_factory(
                    model_field.related_model, seen, flat=True
                ),
                source=model_field.name,
            )

            camel_id_name = snake_to_camel_case(model_field.attname)
            fields.append(camel_id_name)

            if model_field.attname != camel_id_name:
                extra_kwargs[camel_id_name] = {"source": model_field.attname}

    fields.append(camel_name)
    if orig_name != camel_name:
        extra_kwargs[camel_name] = {"source": model_field.name}


def generate_embedded_relations(model, fields, new_attrs):
    schema_fields = {format_field_name(f._name): f for f in model._table_schema.fields}
    for item in model._meta.related_objects:
        # Do not create fields for django-created relations.
        if item.name in schema_fields and schema_fields[item.name].is_nested_table:
            related_serialier = serializer_factory(
                model=item.related_model, seen=frozenset(), flat=True
            )
            fields.append(item.name)
            new_attrs[item.name] = related_serialier(many=True)
