"""The data serialization for dynamic models.

The serializers in this package build on top of the :mod:`rest_framework_dso.serializers`,
to integrate the dynamic construction on top of the DSO serializer format.
Other application-specifice logic is also introduced here as well,
e.g. logic that depends on Amsterdam Schema policies. Such logic is *not* implemented
in the DSO base classes as those classes are completely generic.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from functools import lru_cache
from typing import List, Optional, Tuple, Type, Union, cast
from urllib.parse import quote, urlencode

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.reverse import reverse
from rest_framework.serializers import Field, ManyRelatedField
from schematools.contrib.django.factories import is_dangling_model
from schematools.contrib.django.models import (
    DynamicModel,
    LooseRelationField,
    LooseRelationManyToManyField,
)
from schematools.contrib.django.signals import dynamic_models_removed
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
from dso_api.dynamic_api.permissions import (
    filter_unauthorized_expands,
    get_permission_key_for_field,
    get_unauthorized_fields,
)
from dso_api.dynamic_api.utils import resolve_model_lookup
from rest_framework_dso.embedding import EmbeddedFieldMatch
from rest_framework_dso.fields import AbstractEmbeddedField, EmbeddedField, EmbeddedManyToManyField
from rest_framework_dso.serializers import DSOModelListSerializer, DSOModelSerializer

MAX_EMBED_NESTING_LEVEL = 2


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


def filter_latest_temporal(queryset: models.QuerySet) -> models.QuerySet:
    """Make sure a queryset will only return the latest temporal models"""
    table_schema = queryset.model.table_schema()
    dataset_schema = queryset.model.get_dataset_schema()
    temporal_config = table_schema.temporal
    if not temporal_config:
        return queryset

    identifier = dataset_schema.identifier
    sequence_name = table_schema.temporal["identifier"]

    # does SELECT DISTINCT ON(identifier) ... ORDER BY identifier, sequence DESC
    return queryset.distinct(identifier).order_by(identifier, f"-{sequence_name}")


def temporal_id_based_fetcher(embedded_field: AbstractEmbeddedField):
    """Helper function to return a fetcher function.
    For temporal data tables, that need to be accessed by identifier only,
    we need to get the objects with the highest sequence number.
    """
    model = embedded_field.related_model
    is_loose = embedded_field.is_loose

    def _fetcher(id_list):
        if is_loose:
            identifier = model.get_dataset_schema().identifier
            return filter_latest_temporal(model.objects).filter(**{f"{identifier}__in": id_list})
        else:
            return model.objects.filter(pk__in=id_list)

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
        if request.table_temporal_slice is not None:
            key = request.table_temporal_slice["key"]
            q_params[key] = request.table_temporal_slice["value"]

        query_string = ("&" if "?" in url else "?") + urlencode(q_params)
        return {"count": value.count(), "href": f"{url}{query_string}"}


class DynamicListSerializer(DSOModelListSerializer):
    """This serializer class is used internally when :class:`DynamicSerializer`
    is initialized with the ``many=True`` init kwarg to process a list of objects.
    """

    def get_prefetch_lookups(self) -> List[Union[models.Prefetch, str]]:
        """Optimize M2M prefetch lookups to return latest temporal records only."""
        parent_model = self.child.Meta.model
        lookups = super().get_prefetch_lookups()

        for i, lookup in enumerate(lookups):
            related_model, is_many = resolve_model_lookup(parent_model, lookup)
            if cast(DynamicModel, related_model).is_temporal() and is_many:
                # When the model is a temporal relationship, make sure the prefetch only
                # returns the latest objects. The Prefetch objects allow adding these filters.
                lookups[i] = models.Prefetch(
                    lookup, queryset=filter_latest_temporal(related_model.objects)
                )
        return lookups

    @cached_property
    def expanded_fields(self) -> List[EmbeddedFieldMatch]:
        """Filter unauthorized fields from the matched expands."""
        auto_expand_all = self.fields_to_expand is True
        return filter_unauthorized_expands(
            self.context["request"],
            expanded_fields=super().expanded_fields,
            skip_unauth=auto_expand_all,
        )


class DynamicSerializer(DSOModelSerializer):
    """The logic for dynamically generated serializers.

    Most DSO-related logic is found in the base class
    :class:`~rest_framework_dso.serializers.DSOModelSerializer`.
    This class adds more application-specific logic to the serializer such as:

    * Logic that depends on Amsterdam Schema data.
    * Permissions based on the schema.
    * Temporal relations (ideally in DSO, but highly dependent on schema data).
    * The ``_links`` section logic (depends on knowledge of temporal relations).

    A part of the serializer construction happens here
    (the Django model field -> serializer field translation).
    The remaining part happens in :func:`serializer_factory`.
    """

    _default_list_serializer_class = DynamicListSerializer

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

    def get_request(self):
        """
        Get request from this or parent instance.
        """
        return self.context["request"]

    def get_fields(self):
        """Remove fields that shouldn't be part of the response."""
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

    @cached_property
    def expanded_fields(self) -> List[EmbeddedFieldMatch]:
        """Filter unauthorized fields from the matched expands."""
        auto_expand_all = self.fields_to_expand is True
        return filter_unauthorized_expands(
            self.get_request(),
            expanded_fields=super().expanded_fields,
            skip_unauth=auto_expand_all,
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_schema(self, instance):
        """The schema field is exposed with every record"""
        name = instance.get_dataset_id()
        table = instance.get_table_id()
        url_parts = [name]
        url_prefix = instance.get_dataset().url_prefix
        if url_prefix:
            url_parts.insert(0, url_prefix.strip("/"))
        else:
            url_parts.append(name)

        return f"https://schemas.data.amsterdam.nl/datasets/{'/'.join(url_parts)}#{table}"

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
        if field_class == HyperlinkedRelatedField and model_class.table_schema().is_temporal:
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
                related_ds = field.related_model.get_dataset_schema()
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
                    authorized_data[key] = _mutate_value(permission, data[key])
        return authorized_data


class DynamicBodySerializer(DynamicSerializer):
    """This subclass of the dynamic serializer only exposes the non-relational fields.

    Ideally, this should be obsolete as the serializer_factory() can avoid
    generating those fields in the first place.
    """

    def get_fields(self):
        """Remove fields that shouldn't be in the body."""
        fields = super().get_fields()

        # Pass the current state to the DynamicLinksSerializer instance
        links_field = fields.get("_links")
        if links_field is not None and isinstance(links_field, DynamicLinksSerializer):
            links_field.fields_to_expand = self.fields_to_expand

        hal_fields = self._get_hal_field_names(fields)
        for hal_field in hal_fields:
            fields.pop(hal_field, None)
        return fields

    def _get_hal_field_names(self, fields):  # noqa: C901
        """Get the relational and other identifier fields which should not appear in the body
        but in the respective HAL envelopes in _links
        """
        ds = self.Meta.model.get_dataset_schema()
        table = self.Meta.model.table_schema()
        hal_fields = [ds.identifier]
        temporal = table.temporal
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
    """The serializer for the ``_links`` field.
    Following DSO/HAL guidelines, it contains "self", "schema", and all relational fields.
    """

    serializer_related_field = HALTemporalHyperlinkedRelatedField

    def _include_embedded(self):
        """Never include embedded relations when the
        serializer is used for generating the _links section.
        """
        return False

    def to_representation(self, validated_data):
        """Hide "None" and empty list [] values in the _links section."""
        data = super().to_representation(validated_data)
        return {field: value for field, value in data.items() if value}


def get_view_name(model: Type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param model: The dynamic model.
    :param suffix: This can be "detail" or "list".
    """
    dataset_id = to_snake_case(model.get_dataset_id())
    table_id = to_snake_case(model.get_table_id())
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: serializer_factory.cache_clear())


@lru_cache()
def serializer_factory(
    model: Type[DynamicModel], depth: int = 0, flat: bool = False, nesting_level=0
) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model.

    Internally, this creates all serializer fields based on the metadata
    from the model, and underlying schema definition. It also generates
    a secondary serializer for the ``_links`` field where all relations are exposed.

    Following DSO/HAL guidelines, objects are serialized with ``_links`` and ``_embedded``
    fields, but without relational fields at the top level. The relational fields appear
    either in ``_links`` or in expanded form in ``_embedded``;
    depending on the ``_expand`` and ``_expandScope`` URL parameters.

    :param model: The dynamic model.
    :param depth: Matches the depth parameter for the serializer ``Meta`` field.
      This allows Django Rest Framework to auto-expand relations or omit them.
    :param flat: When true, embedded relations will not be generated.
    """
    if not flat and nesting_level >= MAX_EMBED_NESTING_LEVEL:
        # Won't auto-correct this, as it would open up cache bypassing for lru_cache()
        raise ValueError("flat should be False when nesting exceeds max nesting level")

    _validate_model(model)
    prefix = "Flat" if flat else ""

    if model.has_parent_table():
        # Inner tables have no schema or links defined
        fields = []
    else:
        fields = [
            "_links",
        ]

    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name = f"{prefix}{safe_dataset_id.title()}{model.__name__}Serializer"
    table_schema = model.table_schema()
    new_attrs = {
        "table_schema": table_schema,
        "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
        "__doc__": table_schema.get(
            "description", table_schema.name
        ),  # avoid exposing our docstrings.
    }

    # Parse fields for serializer
    extra_kwargs = {"depth": depth}  # 0 or 1
    for model_field in model._meta.get_fields():
        field_camel_case = toCamelCase(model_field.name)

        # Exclusions:
        if (
            # Do not render PK and FK to parent on nested tables
            (model.has_parent_table() and model_field.name in ["id", "parent"])
            # "identificatie", "volgnummer" are part of `_links.self` only
            # Yet "id" / "pk" is still part of the main body.
            or (table_schema.temporal and field_camel_case in table_schema.identifier)
        ):
            continue

        if isinstance(model_field, models.ManyToOneRel):
            # Reverse relations are still part of the main body
            _build_serializer_reverse_fk_field(model, model_field, new_attrs, fields)
        else:
            _build_serializer_field(
                model, model_field, flat, nesting_level, new_attrs, fields, extra_kwargs
            )

    if not flat:
        _generate_embedded_relations(model, fields, new_attrs, nesting_level)

    if "_links" in fields:
        # Generate the serializer for the _links field containing the relations according to HAL.
        # This is attached as a normal field, so it's recognized by prefetch optimizations.
        new_attrs["_links"] = _links_serializer_factory(model, depth)(source="*")

    # Generate Meta section and serializer class
    new_attrs["Meta"] = type(
        "Meta", (), {"model": model, "fields": fields, "extra_kwargs": extra_kwargs}
    )

    return type(serializer_name, (DynamicBodySerializer,), new_attrs)


def _validate_model(model: Type[DynamicModel]):
    if isinstance(model, str):
        raise ImproperlyConfigured(f"Model {model} could not be resolved.")
    elif not issubclass(model, DynamicModel):
        # Also protects against tests that use a SimpleLazyObject, to avoid bypassing lru_cache()
        raise TypeError(f"serializer_factory() didn't receive a model: {model!r}")
    elif is_dangling_model(model):
        raise RuntimeError("serializer_factory() received an older model reference")


def _links_serializer_factory(model: Type[DynamicModel], depth: int) -> Type[DynamicSerializer]:
    """Generate the DRF serializer class for the ``_links`` section."""
    fields = [
        "schema",
        "self",
    ]

    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}LinksSerializer"
    new_attrs = {
        "table_schema": model.table_schema(),
        "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
    }

    # Parse fields for serializer
    extra_kwargs = {"depth": depth}  # 0 or 1
    for model_field in model._meta.get_fields():
        # Only create fields for relations, avoid adding non-relation fields in _links.
        if isinstance(model_field, models.ManyToOneRel):
            _build_serializer_reverse_fk_field(model, model_field, new_attrs, fields)
        elif isinstance(model_field, (RelatedField, ForeignObjectRel, LooseRelationField)):
            _build_plain_serializer_field(model_field, fields, extra_kwargs)

    # Generate Meta section and serializer class
    new_attrs["Meta"] = type(
        "Meta", (), {"model": model, "fields": fields, "extra_kwargs": extra_kwargs}
    )

    return type(serializer_name, (DynamicLinksSerializer,), new_attrs)


def _build_serializer_field(
    model: Type[DynamicModel],
    model_field: models.Field,
    flat: bool,
    nesting_level: int,
    new_attrs,
    fields,
    extra_kwargs,
):
    """Build a serializer field, results are written in 'output' parameters"""
    # Add extra embedded part for related fields
    # For NM relations, we need another type of EmbeddedField
    if not flat and isinstance(
        model_field,
        (
            models.ForeignKey,
            models.ManyToManyField,
            LooseRelationField,
            LooseRelationManyToManyField,
        ),
    ):
        # Embedded relations are only added to the main serializer.
        _build_serializer_embeddded_field(model_field, nesting_level, new_attrs)

        if isinstance(model_field, LooseRelationField):
            # For loose relations, add an id char field.
            _build_serializer_loose_relation_id_field(model_field, fields, new_attrs)
        else:
            _build_serializer_related_id_field(model_field, fields, extra_kwargs)
    else:
        # Regular fields
        # Re-map file to correct serializer
        field_schema = model.table_schema().get_field_by_id(model_field.name)
        if (
            field_schema is not None
            and field_schema.type == "string"
            and field_schema.format == "blob-azure"
        ):
            _build_serializer_blob_field(model_field, field_schema, fields, new_attrs)

    # Regular fields for the body, and some relation fields
    _build_plain_serializer_field(model_field, fields, extra_kwargs)


def _build_serializer_embeddded_field(
    model_field: Union[RelatedField, LooseRelationField], nesting_level, new_attrs
):
    """Build a embedded field for the serializer"""
    camel_name = toCamelCase(model_field.name)
    EmbeddedFieldClass = (
        EmbeddedManyToManyField
        if isinstance(model_field, models.ManyToManyField)
        else EmbeddedField
    )

    new_attrs[camel_name] = EmbeddedFieldClass(
        serializer_class=serializer_factory(
            model_field.related_model,
            depth=1,
            flat=(nesting_level + 1) >= MAX_EMBED_NESTING_LEVEL,
            nesting_level=nesting_level + 1,
        ),
        source=model_field.name,
    )


def _build_plain_serializer_field(model_field, fields, extra_kwargs):
    """Add the field to the output parameters"""
    camel_name = toCamelCase(model_field.name)
    fields.append(camel_name)

    if model_field.name != camel_name:
        extra_kwargs[camel_name] = {"source": model_field.name}


def _build_serializer_related_id_field(model_field, fields, extra_kwargs):
    """Build the ``FIELD_id`` field for an related field."""
    camel_id_name = toCamelCase(model_field.attname)
    fields.append(camel_id_name)

    if model_field.attname != camel_id_name:
        extra_kwargs[camel_id_name] = {"source": model_field.attname}


def _build_serializer_loose_relation_id_field(model_field, fields, new_attrs):
    """Build the ``FIELD_id`` field for a loose relation."""
    camel_name = toCamelCase(model_field.name)
    loose_id_field_name = f"{camel_name}Id"
    new_attrs[loose_id_field_name] = serializers.CharField(source=model_field.name)
    fields.append(loose_id_field_name)


def _build_serializer_blob_field(model_field, field_schema, fields, new_attrs):
    """Build the blob field"""
    camel_name = toCamelCase(model_field.name)
    new_attrs[camel_name] = AzureBlobFileField(
        account_name=field_schema["account_name"],
        source=(model_field.name if model_field.name != camel_name else None),
    )


def _build_serializer_reverse_fk_field(model, model_field: models.ManyToOneRel, new_attrs, fields):
    """Build the ManyToOneRel field"""
    table_schema = model.table_schema()
    match = _find_reverse_fk_relation(table_schema, model_field)
    if match is None:
        return

    name, relation = match
    format1 = relation.get("format", "summary")
    att_name = model_field.name

    if format1 == "embedded":
        view_name = "dynamic_api:{}-{}-detail".format(
            to_snake_case(model.get_dataset_id()),
            to_snake_case(model_field.related_model.table_schema().id),
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


def _find_reverse_fk_relation(
    table_schema: DatasetTableSchema, model_field: models.ManyToOneRel
) -> Optional[Tuple[str, dict]]:
    """Find the definition of the ManyToOne relation in the schema object."""
    expect_table = toCamelCase(model_field.related_model._meta.model_name)
    expect_field = toCamelCase(model_field.field.name)
    return next(
        (
            (name, relation)
            for name, relation in table_schema.relations.items()
            if relation["table"] == expect_table and relation["field"] == expect_field
        ),
        None,
    )


def _generate_embedded_relations(model, fields, new_attrs, nesting_level):
    schema_fields = {to_snake_case(f.name): f for f in model.table_schema().fields}
    for item in model._meta.related_objects:
        # Do not create fields for django-created relations.
        if item.name in schema_fields and schema_fields[item.name].is_nested_table:
            related_serializer = serializer_factory(
                item.related_model,
                flat=(nesting_level + 1) >= MAX_EMBED_NESTING_LEVEL,
                nesting_level=nesting_level + 1,
            )
            fields.append(item.name)
            new_attrs[item.name] = related_serializer(many=True)


def _mutate_value(permission, value):
    params = None
    if ":" in permission:
        permission, params = permission.split(":")

    if permission == "letters":
        return value[0 : int(params)]
    elif permission == "read":
        return value
    else:
        raise NotImplementedError(f"Invalid permission {permission}")
