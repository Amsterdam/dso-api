from __future__ import annotations

import re
from collections import OrderedDict
from functools import lru_cache
from typing import Type
from urllib.parse import quote, urlencode

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils.functional import cached_property
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.reverse import reverse
from rest_framework.serializers import Field, ManyRelatedField
from schematools.contrib.django.models import (
    DynamicModel,
    LooseRelationField,
    LooseRelationManyToManyField,
)
from schematools.types import DatasetTableSchema
from schematools.utils import to_snake_case, toCamelCase

from dso_api.dynamic_api.fields import (
    AzureBlobFileField,
    HALLooseRelationUrlField,
    HALTemporalHyperlinkedRelatedField,
    LooseRelationUrlField,
    LooseRelationUrlListField,
    TemporalHyperlinkedRelatedField,
    TemporalLinksField,
    TemporalReadOnlyField,
)
from dso_api.dynamic_api.permissions import get_permission_key_for_field, get_unauthorized_fields
from rest_framework_dso.fields import EmbeddedField, EmbeddedManyToManyField
from rest_framework_dso.serializers import DSOModelSerializer


class URLencodingURLfields:
    """ URL encoding mechanism for URL content """

    def to_representation(self, fields_to_be_encoded: list, data):
        for field_name in fields_to_be_encoded:
            try:
                protocol_uri = re.search("([a-z,A-z,0-9,:/]+)(.*)", data[field_name])
                protocol = protocol_uri.group(1)
                uri = protocol_uri.group(2)
                data[field_name] = protocol + quote(uri)
            except (TypeError, AttributeError):
                data = data
        return data


def temporal_id_based_fetcher(model, is_loose=False):
    """Helper function to return a fetcher function.
    For temporal data tables, that need to be accessed by identifier only,
    we need to get the objects with the highest sequence number.
    """

    def _fetcher(id_list):
        if is_loose:
            # We assume temporal config is available in the dataset
            dataset = model.get_dataset()
            identifier = dataset.identifier
            sequence_name = dataset.temporal["identifier"]
            return (
                model.objects.distinct(identifier)  # does SELECT DISTINCT ON(identifier)
                .filter(**{f"{identifier}__in": id_list})
                .order_by(identifier, f"-{sequence_name}")
                .iterator()
            )
        else:
            return model.objects.filter(pk__in=id_list).iterator()

    return _fetcher


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
    def to_representation(self, value: models.Manager):
        request = self.context["request"]
        url = reverse(get_view_name(value.model, "list"), request=request)
        filter_field = next(iter(value.core_filters.keys()))
        q_params = {toCamelCase(filter_field + "_id"): value.instance.pk}

        # If this is a temporary slice, add the extra parameter to the qs.
        if request.dataset_temporal_slice is not None:
            key = request.dataset_temporal_slice["key"]
            q_params[key] = request.dataset_temporal_slice["value"]

        query_string = ("&" if "?" in url else "?") + urlencode(q_params)
        return {"count": value.count(), "href": f"{url}{query_string}"}


class DynamicSerializer(DSOModelSerializer):
    """Base class for all generic serializers of this package."""

    serializer_url_field = DynamicLinksField
    serializer_field_mapping = {
        **DSOModelSerializer.serializer_field_mapping,
        LooseRelationField: HALLooseRelationUrlField,
        LooseRelationManyToManyField: LooseRelationUrlListField,
    }

    schema = serializers.SerializerMethodField()

    _links = serializers.SerializerMethodField()

    table_schema: DatasetTableSchema = None

    id_based_fetcher = staticmethod(temporal_id_based_fetcher)
    hal_relations_serializer_class = None

    def get_request(self):
        """
        Get request from this or parent instance.
        """
        return self.context["request"]

    def get_fields(self):
        fields = super().get_fields()
        request = self.get_request()

        # Adjust the serializer based on the request.
        # request can be None for get_schema_view(public=True)
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

    @cached_property
    def hal_relations_serializer(self):
        # Serializer needs to be instantiated once, so it also determines it's .fields once.
        # Otherwise, the cached properties on that class are recalculated per object in a list.
        return self.hal_relations_serializer_class(
            context=self.context, fields_to_expand=self.fields_to_expand
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get__links(self, instance):
        return self.hal_relations_serializer.to_representation(instance)

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
        field_class, field_kwargs = super().build_relational_field(field_name, relation_info)
        if "view_name" in field_kwargs:
            model_class = relation_info[1]
            field_kwargs["view_name"] = get_view_name(model_class, "detail")

        # Only make it a temporal field if model is from a temporal dataset
        if field_class == HyperlinkedRelatedField and model_class._table_schema.is_temporal:
            field_class = TemporalHyperlinkedRelatedField
        return field_class, field_kwargs

    def build_property_field(self, field_name, model_class):
        field_class, field_kwargs = super().build_property_field(field_name, model_class)
        forward_map = model_class._meta._forward_fields_map.get(field_name)
        if forward_map and isinstance(forward_map, models.ForeignKey):
            field_class = TemporalReadOnlyField

        return field_class, field_kwargs

    @cached_property
    def _loose_relation_m2m_fields(self):
        """The M2M field metadata, retrieved once for this serializer.
        The caching makes sure this is only calculated once in a list serializer.
        """
        from .urls import app_name

        result = []
        for f in self.Meta.model._meta.many_to_many:
            field = self.Meta.model._meta.get_field(f.attname)
            if isinstance(field, LooseRelationManyToManyField):
                dataset_name, table_name = [
                    to_snake_case(part) for part in field.relation.split(":")
                ]
                url_name = f"{app_name}:{dataset_name}-{table_name}-detail"
                related_ds = field.related_model.get_dataset()
                related_identifier_field = related_ds.identifier
                result.append(
                    (f.attname, toCamelCase(f.attname), url_name, related_identifier_field)
                )

        return result

    def to_representation(self, validated_data):
        data = super().to_representation(validated_data)

        request = self.get_request()

        # URL encoding of the data, i.e. spaces to %20, only if urlfield is present
        if self._url_content_fields:
            data = URLencodingURLfields().to_representation(self._url_content_fields, data)

        for (
            attname,
            camel_name,
            url_name,
            related_identifier_field,
        ) in self._loose_relation_m2m_fields:
            if attname in data and not data[camel_name]:
                # TODO: N-query issue, which needs to be addressed later.
                related_mgr = getattr(validated_data, attname)
                related_ids = (
                    related_mgr.through.objects.filter(
                        **{related_mgr.source_field_name: validated_data.id}
                    )
                    .order_by()
                    .values_list(f"{related_mgr.target_field_name}_id", flat=True)
                )

                data[camel_name] = [
                    {
                        "href": reverse(url_name, kwargs={"pk": item}, request=request),
                        "title": item,
                        related_identifier_field: item,
                    }
                    for item in related_ids
                ]

        if self.instance is not None:
            data.update(self._profile_based_authorization_and_mutation(data))
        return data

    def _profile_based_authorization_and_mutation(self, data):
        authorized_data = dict()
        if isinstance(self.instance, list):
            # test workaround
            model = self.instance[0]._meta.model
        elif isinstance(self.instance, models.QuerySet):
            # ListSerializer use
            model = self.instance.model
        else:
            model = self.instance._meta.model
        request = self.get_request()

        for model_field in model._meta.get_fields():
            permission_key = get_permission_key_for_field(model_field)
            permission = request.auth_profile.get_read_permission(permission_key)
            if permission is not None:
                key = toCamelCase(model_field.name)
                if key in data:
                    authorized_data[key] = mutate_value(permission, data[key])
        return authorized_data


class DynamicBodySerializer(DynamicSerializer):
    """Following DSO/HAL guidelines, objects are serialized with _links and _embedded fields,
    but without relational fields at the top level. The relational fields appear either in
    _links or in expanded form in _embedded; depending on the _expand and _expandScope URL
    parameters
    """

    def get_fields(self):
        fields = super().get_fields()
        hal_fields = self._get_hal_field_names(fields)
        for hal_field in hal_fields:
            fields.pop(hal_field, None)
        return fields

    def _get_hal_field_names(self, fields):  # noqa: C901
        """Get the relational and other identifier fields which should not appear in the body
        but in the respective HAL envelopes in _links
        """
        ds = self.Meta.model.get_dataset()
        hal_fields = [ds.identifier]
        temporal = ds.temporal
        if temporal is not None and "identifier" in temporal:
            hal_fields.append(temporal["identifier"])
        capitalized_identifier_fields = [
            identifier_field.capitalize() for identifier_field in hal_fields
        ]
        for field_name, field in fields.items():
            if isinstance(field, TemporalHyperlinkedRelatedField):
                hal_fields.append(field_name)
                hal_fields += [f"{field_name}{suffix}" for suffix in capitalized_identifier_fields]
            elif isinstance(
                field,
                (HyperlinkedRelatedField, ManyRelatedField, LooseRelationUrlField),
            ):
                hal_fields.append(field_name)

        return hal_fields


class DynamicLinksSerializer(DynamicSerializer):
    """The serializer for the _links field. Following DSO/HAL guidelines, it contains "self",
    "schema", and all relational fields that have not been expanded. This depends on the
    _expand and _expandScope URL parameters. When expanded, they move to "_embedded".
    In case of a list-view, keep the relational fields. The resources in "_embedded" are
    grouped together for deduplication purposes and this will allow the user to know which
    embed belongs to which object.
    """

    serializer_related_field = HALTemporalHyperlinkedRelatedField

    def _include_embedded(self):
        """Never include embedded relations when the
        serializer is used for generating the _links section.
        """
        return False

    def get_fields(self):
        fields = super().get_fields()
        link_fields = self._get_link_field_names(fields)
        return OrderedDict([(key, value) for key, value in fields.items() if key in link_fields])

    def _get_link_field_names(self, fields):
        """Get the fields that should appear in the _links section"""
        embedded_fields = self.fields_to_expand
        link_fields = ["self", "schema"]
        relation_fields = [
            field_name
            for field_name, field in fields.items()
            if isinstance(
                field,
                (HyperlinkedRelatedField, ManyRelatedField, LooseRelationUrlField),
            )
        ]
        # add the relation_fields to _links if there is not going to be an _embedded
        # or if we are part of a list-view
        if not embedded_fields or (
            "view" in self.context
            and hasattr(self.context["view"], "detail")
            and not self.context["view"].detail
        ):
            link_fields += relation_fields
        elif isinstance(embedded_fields, list):
            link_fields += [
                field_name for field_name in relation_fields if field_name not in embedded_fields
            ]
        return link_fields


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param suffix: This can be "detail" or "list".
    """
    dataset_id = to_snake_case(model.get_dataset_id())
    table_id = to_snake_case(model.get_table_id())
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


@lru_cache()
def serializer_factory(
    model: Type[DynamicModel], depth: int, flat=None, links_serializer=False
) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model.
    It can generate the serializer for both the body as well as for the _links field,
    depending on links_serializer being False or True."""

    if links_serializer:
        fields = [
            "schema",
            "self",
        ]
    elif depth <= 1:
        fields = [
            "_links",
        ]
    else:
        fields = []

    if isinstance(model, str):
        raise ImproperlyConfigured(f"Model {model} could not be resolved.")
    # Inner tables have no schema or links defined
    if model.has_parent_table():
        fields = []
    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name_ext = "Links" if links_serializer else ""
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}{serializer_name_ext}Serializer"
    new_attrs = {
        "table_schema": model._table_schema,
        "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
    }

    # Parse fields for serializer
    extra_kwargs = {"depth": depth}
    for model_field in model._meta.get_fields():
        _build_serializer_field(
            model, model_field, new_attrs, fields, extra_kwargs, links_serializer
        )

    # Generate embedded relations
    if not flat:
        generate_embedded_relations(model, fields, new_attrs)

    if depth <= 1 and not links_serializer:
        # Generate the serializer for the _links field containing the relations according to HAL
        hal_relations_serializer_class = serializer_factory(
            model, depth, flat=True, links_serializer=True
        )
        new_attrs["hal_relations_serializer_class"] = hal_relations_serializer_class

    # Generate Meta section and serializer class
    new_attrs["Meta"] = type(
        "Meta", (), {"model": model, "fields": fields, "extra_kwargs": extra_kwargs}
    )

    serializer_class = DynamicLinksSerializer if links_serializer else DynamicBodySerializer
    return type(serializer_name, (serializer_class,), new_attrs)


def _build_serializer_field(  # noqa: C901
    model, model_field, new_attrs, fields, extra_kwargs, links_serializer
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
                and relation["table"] == toCamelCase(model_field.related_model._meta.model_name)
                and relation["field"] == toCamelCase(model_field.field.name)
            ):
                format1 = relation.get("format", "summary")
                att_name = model_field.name
                if format1 == "embedded":
                    view_name = "dynamic_api:{}-{}-detail".format(
                        to_snake_case(model._table_schema.dataset.id),
                        to_snake_case(model_field.related_model._table_schema.id),
                    )
                    new_attrs[name] = HALTemporalHyperlinkedRelatedField(
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

    # Re-map file to correct serializer
    field_schema = model._table_schema.get_field_by_id(model_field.name)
    if field_schema is not None and field_schema.type == "string":
        if field_schema.format == "blob-azure":
            new_attrs[camel_name] = AzureBlobFileField(account_name=field_schema["account_name"])

    # Add extra embedded part for related fields
    # For NM relations, we need another type of EmbeddedField
    if isinstance(
        model_field,
        (
            models.ForeignKey,
            models.ManyToManyField,
            LooseRelationField,
            LooseRelationManyToManyField,
        ),
    ):

        EmbeddedFieldClass = EmbeddedField

        if isinstance(model_field, models.ManyToManyField):
            EmbeddedFieldClass = EmbeddedManyToManyField
        if depth <= 1:
            new_attrs[camel_name] = EmbeddedFieldClass(
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

    if not links_serializer and isinstance(model_field, LooseRelationField):
        # add a loose relation id char field
        loose_id_field_name = f"{camel_name}Id"
        new_attrs[loose_id_field_name] = serializers.CharField(source=model_field.name)
        fields.append(loose_id_field_name)


def generate_embedded_relations(model, fields, new_attrs):
    schema_fields = {to_snake_case(f.name): f for f in model._table_schema.fields}
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

    if permission == "letters":
        return value[0 : int(params)]
    elif permission == "read":
        return value
    else:
        raise NotImplementedError(f"Invalid permission {permission}")
