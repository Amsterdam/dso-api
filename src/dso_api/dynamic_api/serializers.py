from __future__ import annotations

import re
import urllib.parse
from collections import OrderedDict
from functools import lru_cache
from typing import Type

from django.db import models
from django.core.exceptions import ImproperlyConfigured

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.serializers import DSOModelSerializer
from rest_framework.serializers import Field
from rest_framework.reverse import reverse
from schematools.types import DatasetTableSchema
from schematools.contrib.django.models import DynamicModel
from schematools.contrib.django.auth_backend import RequestProfile
from schematools.utils import to_snake_case, toCamelCase

from dso_api.dynamic_api.fields import (
    TemporalHyperlinkedRelatedField,
    TemporalReadOnlyField,
    TemporalLinksField,
)
from dso_api.dynamic_api.permissions import (
    get_unauthorized_fields,
    get_permission_key_for_field,
)


class URLencodingURLfields:
    """ URL encoding mechanism for URL content """

    def to_representation(self, fields_to_be_encoded: list, data):
        for field_name in fields_to_be_encoded:
            protocol_uri = re.search("([a-z,A-z,0-9,:/]+)(.*)", data[field_name])
            protocol = protocol_uri.group(1)
            uri = protocol_uri.group(2)
            data[field_name] = protocol + urllib.parse.quote(uri)
        return data


class DynamicLinksField(TemporalLinksField):
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


class _RelatedSummaryField(Field):
    def to_representation(self, value: DynamicModel):
        count = value.count()
        url = reverse(
            get_view_name(value.model, "list"), request=self.context["request"]
        )
        parent_pk = value.instance.pk
        filter_name = list(value.core_filters.keys())[0] + "Id"
        separator = "&" if "?" in url else "?"
        return {
            "count": count,
            "href": f"{url}{separator}{filter_name}={parent_pk}",
        }


class DynamicSerializer(DSOModelSerializer):
    """Base class for all generic serializers of this package."""

    serializer_url_field = DynamicLinksField

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

        if field_class == HyperlinkedRelatedField:
            field_class = TemporalHyperlinkedRelatedField
        return field_class, field_kwargs

    def build_property_field(self, field_name, model_class):
        field_class, field_kwargs = super().build_property_field(
            field_name, model_class
        )
        forward_map = model_class._meta._forward_fields_map.get(field_name)
        if forward_map and isinstance(forward_map, models.fields.related.ForeignKey):
            field_class = TemporalReadOnlyField

        return field_class, field_kwargs

    def to_representation(self, validated_data):
        data = super().to_representation(validated_data)

        # URL encoding of the data, i.e. spaces to %20, only if urlfield is present
        if self._url_content_fields:
            data = URLencodingURLfields().to_representation(
                self._url_content_fields, data
            )

        if self.instance is not None:
            if isinstance(self.instance, list):
                # test workaround
                model = self.instance[0]._meta.model
            elif isinstance(self.instance, models.QuerySet):
                # ListSerializer use
                model = self.instance.model
            else:
                model = self.instance._meta.model
            request = self.get_request()

            if not hasattr(request, "auth_profile"):
                request.auth_profile = RequestProfile(request)

            for model_field in model._meta.get_fields():
                permission_key = get_permission_key_for_field(model_field)
                permission = request.auth_profile.get_read_permission(permission_key)
                if permission is not None:
                    key = toCamelCase(model_field.name)
                    data[key] = mutate_value(permission, data[key])

        return data


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param suffix: This can be "detail" or "list".
    """
    dataset_id = to_snake_case(model.get_dataset_id())
    table_id = to_snake_case(model.get_table_id())
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


@lru_cache()
def serializer_factory(
    model: Type[DynamicModel], depth: int, flat=None
) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model."""
    fields = ["_links", "schema"]
    if isinstance(model, str):
        raise ImproperlyConfigured(f"Model {model} could not be resolved.")
    # Inner tables have no schema or links defined
    if model.has_parent_table():
        fields = []
    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}Serializer"
    new_attrs = {
        "table_schema": model._table_schema,
        "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
    }

    # Parse fields for serializer
    extra_kwargs = {"depth": depth}
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


def generate_field_serializer(  # noqa: C901
    model, model_field, new_attrs, fields, extra_kwargs
):
    orig_name = model_field.name
    # Instead of having to apply camelize() on every response,
    # create converted field names on the serializer construction.
    camel_name = toCamelCase(model_field.name)
    depth = extra_kwargs.get("depth", 0)
    depth += 1
    if isinstance(model_field, models.ManyToOneRel):
        for name, relation in model._table_schema.relations.items():
            if (
                depth <= 2
                and relation["table"]
                == toCamelCase(model_field.related_model._meta.model_name)
                and relation["field"] == toCamelCase(model_field.field.name)
            ):
                format1 = relation.get("format", "summary")
                att_name = model_field.name
                if format1 == "embedded":
                    view_name = "dynamic_api:{}-{}-detail".format(
                        to_snake_case(model._table_schema.dataset.id),
                        to_snake_case(model_field.related_model._table_schema.id),
                    )
                    new_attrs[name] = TemporalHyperlinkedRelatedField(
                        many=True,
                        view_name=view_name,
                        queryset=getattr(model, att_name),
                    )
                    fields.append(name)
                elif format1 == "summary":
                    new_attrs[name] = _RelatedSummaryField()
                    fields.append(name)
                break
        return
    if model.has_parent_table() and model_field.name in ["id", "parent"]:
        # Do not render PK and FK to parent on nested tables
        return

    # Instead of having to apply camelize() on every response,
    # create converted field names on the serializer construction.
    camel_name = toCamelCase(model_field.name)

    # Add extra embedded part for foreign keys
    if isinstance(model_field, models.ForeignKey):
        if depth <= 1:
            new_attrs[camel_name] = EmbeddedField(
                serializer_class=serializer_factory(
                    model_field.related_model, depth=depth, flat=True
                ),
                source=model_field.name,
            )

            camel_id_name = toCamelCase(model_field.attname)
            fields.append(camel_id_name)

            if model_field.attname != camel_id_name:
                extra_kwargs[camel_id_name] = {"source": model_field.attname}

    fields.append(camel_name)
    if orig_name != camel_name:
        extra_kwargs[camel_name] = {"source": model_field.name}


def generate_embedded_relations(model, fields, new_attrs):
    schema_fields = {to_snake_case(f._name): f for f in model._table_schema.fields}
    for item in model._meta.related_objects:
        # Do not create fields for django-created relations.
        if item.name in schema_fields and schema_fields[item.name].is_nested_table:
            related_serializer = serializer_factory(item.related_model, 0, flat=True)
            fields.append(item.name)
            new_attrs[item.name] = related_serializer(many=True)


def mutate_value(permission, value):
    params = None
    if ":" in permission:
        permission, params = permission.split(":")
    return {
        "letters": lambda data, count: data[0 : int(count)],
        "read": lambda data, _: data,
    }[permission](value, params)
