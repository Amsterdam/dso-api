"""The data serialization for dynamic models.

The serializers in this package build on top of the :mod:`rest_framework_dso.serializers`,
to integrate the dynamic construction on top of the DSO serializer format.
Other application-specifice logic is also introduced here as well,
e.g. logic that depends on Amsterdam Schema policies. Such logic is *not* implemented
in the DSO base classes as those classes are completely generic.
"""
from __future__ import annotations

import logging
import re
from functools import wraps
from typing import Any, Callable, Union, cast
from urllib.parse import quote, urlencode

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import SimpleLazyObject, cached_property
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field, inline_serializer
from more_itertools import first
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.reverse import reverse
from rest_framework.serializers import Field
from schematools.contrib.django.factories import is_dangling_model
from schematools.contrib.django.models import (
    DynamicModel,
    LooseRelationField,
    LooseRelationManyToManyField,
    get_field_schema,
)
from schematools.contrib.django.signals import dynamic_models_removed
from schematools.types import DatasetTableSchema, Json, Temporal
from schematools.utils import to_snake_case, toCamelCase

from dso_api.dynamic_api.fields import (
    AzureBlobFileField,
    HALLooseRelationUrlField,
    HALTemporalHyperlinkedRelatedField,
    LooseRelationUrlListField,
    TemporalHyperlinkedRelatedField,
    TemporalLinksField,
    TemporalReadOnlyField,
)
from dso_api.dynamic_api.permissions import filter_unauthorized_expands
from dso_api.dynamic_api.utils import resolve_model_lookup
from rest_framework_dso.embedding import EmbeddedFieldMatch
from rest_framework_dso.fields import AbstractEmbeddedField, get_embedded_field_class
from rest_framework_dso.serializers import DSOModelListSerializer, DSOModelSerializer

MAX_EMBED_NESTING_LEVEL = 10
logger = logging.getLogger(__name__)


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
    temporal_config = table_schema.temporal
    if not temporal_config:
        return queryset

    identifier = first(table_schema.identifier)
    sequence_name = table_schema.temporal.identifier

    # does SELECT DISTINCT ON(identifier) ... ORDER BY identifier, sequence DESC
    return queryset.distinct(identifier).order_by(identifier, f"-{sequence_name}")


def temporal_id_based_fetcher(embedded_field: AbstractEmbeddedField):
    """Helper function to return a fetcher function.
    For temporal data tables, that need to be accessed by identifier only,
    we need to get the objects with the highest sequence number.
    """
    model = embedded_field.related_model
    is_loose = embedded_field.is_loose

    def _fetcher(id_list, id_field=None):
        if is_loose:
            identifier = id_field or first(model.table_schema().identifier)
            base_qs = filter_latest_temporal(model.objects)
        else:
            identifier = id_field or "pk"
            base_qs = model.objects

        return base_qs.filter(**{f"{identifier}__in": id_list})

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


@extend_schema_field(
    # Tell what this field will generate as object structure
    inline_serializer(
        "RelatedSumary",
        fields={
            "count": serializers.IntegerField(),
            "href": serializers.URLField(),
        },
    ),
    component_name="RelatedSummary",
)
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

    def get_prefetch_lookups(self) -> list[Union[models.Prefetch, str]]:
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
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        """Filter unauthorized fields from the matched expands."""
        return filter_unauthorized_expands(
            self.context["request"].user_scopes,
            expanded_fields=super().expanded_fields,
            skip_unauth=self.expand_scope.auto_expand_all,
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

    def get_fields(self) -> dict[str, serializers.Field]:
        """Override DRF to remove fields that shouldn't be part of the response."""
        user_scopes = self.get_request().user_scopes
        model = self.Meta.model

        # See what fields should really be included.
        fields = {}
        for field_name, field in super().get_fields().items():
            if field.source == "*":
                # e.g. _links field, always include. These sub serializers
                # do their own permission checks for their fields.
                fields[field_name] = field
                continue

            # field.source can be None as this point, because Field.bind() is not called yet.
            model_field = model._meta.get_field(field.source or field_name)
            field_schema = get_field_schema(model_field)
            if permission := user_scopes.has_field_access(field_schema):
                # field has permission
                if transform_function := permission.transform_function():
                    # Value must be transformed, decorate to_representation() for it.
                    # Fields are a deepcopy, so this doesn't affect other serializer instances.
                    # This strategy also avoids having to dig into the response data afterwards.
                    field.to_representation = self._apply_transform(
                        field.to_representation, transform_function
                    )

                fields[field_name] = field

        return fields

    @staticmethod
    def _apply_transform(
        to_representation: Callable[[Any], Json], transform_function: Callable[[Json], Json]
    ):
        """Make sure an additional transformation happens before the field generated output.
        :param to_representation: The bound method from the serializer
        :param transform_function: A function that adjusts the rendered value.
        """

        @wraps(to_representation)
        def _new_to_representation(data):
            value = to_representation(data)
            return transform_function(value)

        return _new_to_representation

    @cached_property
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        """Filter unauthorized fields from the matched expands."""
        return filter_unauthorized_expands(
            self.get_request().user_scopes,
            expanded_fields=super().expanded_fields,
            skip_unauth=self.expand_scope.auto_expand_all,
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_schema(self, instance):
        """The schema field is exposed with every record"""
        table = instance.get_table_id()
        dataset_path = instance.get_dataset_path()
        return f"https://schemas.data.amsterdam.nl/datasets/{dataset_path}/dataset#{table}"

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

                dataset_name, table_name = (
                    to_snake_case(part) for part in field.relation.split(":")
                )
                url_name = f"{app_name}:{dataset_name}-{table_name}-detail"
                related_table = field.related_model.table_schema()

                related_identifier_field = first(related_table.identifier)
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

        return data


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
            links_field.expand_scope = self.expand_scope

        return fields


class DynamicLinksSerializer(DynamicSerializer):
    """The serializer for the ``_links`` field.
    Following DSO/HAL guidelines, it contains "self", "schema", and all relational fields.
    """

    serializer_related_field = HALTemporalHyperlinkedRelatedField

    def get_fields(self) -> dict[str, serializers.Field]:
        """Override to avoid adding fields that loop back to a parent."""
        fields = super().get_fields()

        if self.parent_source_fields:
            for name, field in fields.copy().items():
                if self._is_repeated_relation(name, field):
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Excluded %s from _links field, it resolves to a parent via %s.%s",
                            name,
                            ".".join(f.name for f in self.parent_source_fields),
                            field.source,
                        )
                    del fields[name]

        return fields

    @cached_property
    def parent_source_fields(
        self,
    ) -> list[Union[RelatedField, LooseRelationField, ForeignObjectRel]]:
        """Find the ORM relationship fields that lead to this serializer instance"""
        source_fields = []
        parent = self.parent

        # The root-level obviously doesn't have a field name,
        # hence the check for parent.parent to exclude the root object.
        while parent.parent is not None:
            if parent.source_attrs and hasattr(parent.parent, "Meta"):
                model = parent.parent.Meta.model

                for attr in parent.source_attrs:
                    field = model._meta.get_field(attr)
                    source_fields.append(field)
                    model = field.related_model

            parent = parent.parent
        return source_fields

    def _is_repeated_relation(self, name: str, field: serializers.Field) -> bool:
        """Check whether the field references back to a parent relation.
        This detects whether the field is a relation, and whether it's model fields
        are references by the pre-calculated `source_fields`.
        """
        if field.source == "*" or not isinstance(
            field,
            (serializers.ModelSerializer, serializers.RelatedField, serializers.ManyRelatedField),
        ):
            return False

        # Resolve the model field that this serializer field links to.
        # The source_attrs is generated here as it's created later in field.bind().
        source_attrs = (field.source or name).split(".")
        model = self.Meta.model
        for attr in source_attrs:
            model_field = model._meta.get_field(attr)
            model = model_field.related_model  # for deeper nesting

            # Check whether the reverse relation of that model field
            # is already walked through by a parent serializer
            if (
                model_field.remote_field is not None
                and model_field.remote_field in self.parent_source_fields
            ):
                return True

        return False

    def _include_embedded(self):
        """Never include embedded relations when the
        serializer is used for generating the _links section.
        """
        return False

    def to_representation(self, validated_data):
        """Hide "None" and empty list [] values in the _links section."""
        data = super().to_representation(validated_data)
        return {field: value for field, value in data.items() if value}


def get_view_name(model: type[DynamicModel], suffix: str):
    """Return the URL pattern for a dynamically generated model.

    :param model: The dynamic model.
    :param suffix: This can be "detail" or "list".
    """
    dataset_id = to_snake_case(model.get_dataset_id())
    table_id = to_snake_case(model.get_table_id())
    return f"dynamic_api:{dataset_id}-{table_id}-{suffix}"


class ThroughSerializer(DynamicSerializer):
    """The serializer for the through table of M2M relations.

    Because temporal fields can be defined 'on the relation', like e.g.
    beginGeldigheid and eindGeldigheid, we need a separate serializer.
    For the 'target' of the M2M relation the HALTemporalHyperlinkedRelatedField
    is used. This field is added in the factory for this serializer.

    The content of this field is merged into this serializer.
    To be able to fetch this field, a special attribute `target_field_name`
    is added to the `Meta` object of this serializer.

    """

    serializer_related_field = HALTemporalHyperlinkedRelatedField

    def to_representation(self, obj):
        """Move output of field named target_field_name to this representation."""
        representation = super().to_representation(obj)

        target_representation = representation.pop(self.Meta.target_field_name)

        # if data is incomplete, target_representation could be None
        # avoid crash
        if target_representation is not None:
            representation.update(target_representation)

        return representation


# When models are removed, clear the cache.
serializer_factory_cache = LRUCache(maxsize=100000)
dynamic_models_removed.connect(lambda **kwargs: serializer_factory_cache.clear())


def _serializer_cache_key(model, depth=0, nesting_level=0):
    """The cachetools allow definining the cache key,
    so the nesting level does not bypass the cache which it would with lru_cache().
    """
    return hashkey(model, depth)


class SerializerAssemblyLine:
    """The intermediate result of the serializer factory"""

    def __init__(
        self,
        model: type[DynamicModel],
        fields=None,
        depth: int = 0,
        openapi_docs: str = "",
        **meta_kwargs,
    ):
        """
        :param model: The model for which this serializer is created.
        :param depth: Define whether Django REST Framework should expand or omit relations.
                      Typically it's either 0 or 1.
        """
        safe_dataset_id = to_snake_case(model.get_dataset_id())
        self.class_attrs = {
            "__module__": f"dso_api.dynamic_api.serializers.{safe_dataset_id}",
            "__doc__": openapi_docs,  # avoid exposing our docstrings.
            "table_schema": model.table_schema(),
            "Meta": type(
                "Meta",
                (),
                {
                    "model": model,
                    "fields": fields or [],
                    "extra_kwargs": {"depth": depth},
                    "embedded_fields": {},
                    **meta_kwargs,
                },
            ),
        }

    def add_field(self, name, field: serializers.Field):
        """Add a field to the serializer assembly"""
        self.class_attrs[name] = field
        self.class_attrs["Meta"].fields.append(name)

    def add_field_name(self, name, *, source=None):
        """Add a field, but only by name.
        The regular DRF ModelSerializer will generate the field (at every request!).
        """
        self.class_attrs["Meta"].fields.append(name)
        if source is not None and source != name:
            self.class_attrs["Meta"].extra_kwargs[name] = {"source": source}

    def add_embedded_field(self, name, field: AbstractEmbeddedField):
        """Add an embedded field to the serializer-to-be."""
        # field.__set_name__() handling will be triggered on class construction.
        self.class_attrs[name] = field

    def construct_class(
        self, class_name, base_class: type[DynamicSerializer]
    ) -> type[DynamicSerializer]:
        """Perform dynamic class construction"""
        return type(class_name, (base_class,), self.class_attrs)


@cached(cache=serializer_factory_cache, key=_serializer_cache_key)
def serializer_factory(
    model: type[DynamicModel], depth: int = 0, nesting_level=0
) -> type[DynamicSerializer]:
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
    """
    if nesting_level >= MAX_EMBED_NESTING_LEVEL:
        raise RuntimeError("recursion in embedded nesting")

    _validate_model(model)

    # Get model data
    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}Serializer"
    table_schema = model.table_schema()

    # Start the assemblage of the serializer
    serializer_part = SerializerAssemblyLine(
        model, depth=depth, openapi_docs=table_schema.get("description", table_schema.name)
    )

    if not model.has_parent_table():
        # Inner tables have no schema or links defined
        # Generate the serializer for the _links field containing the relations according to HAL.
        # This is attached as a normal field, so it's recognized by prefetch optimizations.
        serializer_part.add_field("_links", _links_serializer_factory(model, depth)(source="*"))

    # Debug how deep serializers are created, debug circular references
    logger.debug(
        "%sserializer_factory() %s %s %d",
        " " * nesting_level,
        serializer_name,
        model.__name__,
        nesting_level,
    )

    if table_schema.temporal:
        unwanted_identifiers = list(map(toCamelCase, table_schema.identifier))
    else:
        unwanted_identifiers = []

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        field_camel_case = toCamelCase(model_field.name)
        field_schema = get_field_schema(model_field)

        # Exclusions:
        if (
            # Do not render PK and FK to parent on nested tables
            (model.has_parent_table() and model_field.name in ["id", "parent"])
            # Do not render temporal "identificatie" or "volgnummer" fields.
            # Yet "id" / "pk" is still part of the main body.
            or (table_schema.temporal and field_camel_case in unwanted_identifiers)
            # Do not render intermediate keys "relation_identificatie" / "relation_volgnummer"
            or (
                field_schema.parent_field is not None
                and field_schema.parent_field.is_through_table
            )
        ):
            continue

        _build_serializer_field(serializer_part, model_field, nesting_level)

    _generate_nested_relations(serializer_part, model, nesting_level)

    # Generate Meta section and serializer class
    return serializer_part.construct_class(serializer_name, base_class=DynamicBodySerializer)


def _validate_model(model: type[DynamicModel]):
    if isinstance(model, str):
        raise ImproperlyConfigured(f"Model {model} could not be resolved.")
    elif not issubclass(model, DynamicModel):
        # Also protects against tests that use a SimpleLazyObject, to avoid bypassing lru_cache()
        raise TypeError(f"serializer_factory() didn't receive a model: {model!r}")
    elif is_dangling_model(model):
        raise RuntimeError("serializer_factory() received an older model reference")


def _links_serializer_factory(model: type[DynamicModel], depth: int) -> type[DynamicSerializer]:
    """Generate the DRF serializer class for the ``_links`` section."""
    safe_dataset_id = to_snake_case(model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{model.__name__}LinksSerializer"

    serializer_part = SerializerAssemblyLine(
        model,
        fields=["schema", "self"],
        openapi_docs=(
            f"The contents of the `{model.table_schema().name}._links` field."
            " It contains all relationships with objects."
        ),
        depth=depth,
    )

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        # Only create fields for relations, avoid adding non-relation fields in _links.
        if isinstance(model_field, models.ManyToOneRel):
            _build_serializer_reverse_fk_field(serializer_part, model, model_field)
        # We need to handle LooseRelationManyToManyField first, because
        # it is also a subclass of the regular ManyToManyField
        elif isinstance(model_field, LooseRelationManyToManyField):
            _build_plain_serializer_field(serializer_part, model_field)
        elif isinstance(model_field, models.ManyToManyField):
            _build_m2m_serializer(serializer_part, model, model_field)
        elif isinstance(model_field, (RelatedField, ForeignObjectRel, LooseRelationField)):
            _build_plain_serializer_field(serializer_part, model_field)

    # Generate serializer class
    return serializer_part.construct_class(serializer_name, base_class=DynamicLinksSerializer)


def _build_serializer_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field, nesting_level: int
):  # noqa: C901
    """Build a serializer field, results are written in 'output' parameters"""
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
        # Embedded relations are only added to the main serializer.
        _build_serializer_embedded_field(serializer_part, model_field, nesting_level)

        if isinstance(model_field, LooseRelationField):
            # For loose relations, add an id char field.
            _build_serializer_loose_relation_id_field(serializer_part, model_field)
        elif isinstance(model_field, models.ForeignKey):
            # Forward relation, add an id field in the main body.
            _build_serializer_related_id_field(serializer_part, model_field)
        return
    elif isinstance(model_field, ForeignObjectRel):
        # Reverse relations, are only added as embedded field when there is an explicit declaration
        field_schema = get_field_schema(model_field)
        additional_relation = field_schema.reverse_relation
        if additional_relation is None or additional_relation.format == "summary":
            return
        _build_serializer_embedded_field(serializer_part, model_field, nesting_level)
    elif not isinstance(model_field, models.AutoField):
        # Regular fields
        # Re-map file to correct serializer
        field_schema = get_field_schema(model_field)
        if field_schema.type == "string" and field_schema.format == "blob-azure":
            _build_serializer_blob_field(serializer_part, model_field, field_schema)
            return

    if model_field.is_relation:
        return

    # Regular fields for the body, and some relation fields
    _build_plain_serializer_field(serializer_part, model_field)


def _build_serializer_embedded_field(
    serializer_part: SerializerAssemblyLine,
    model_field: Union[RelatedField, LooseRelationField, ForeignObjectRel],
    nesting_level: int,
):
    """Build a embedded field for the serializer"""
    EmbeddedFieldClass = get_embedded_field_class(model_field)

    # The serializer class is not actually created here, this happens on-demand.
    # This avoids deep recursion (e.g. 9 levels deep) of the same serializer class
    # when there is a circular reference. During recursion, the LRU-cache is not yet filled.
    serializer_class = SimpleLazyObject(
        lambda: serializer_factory(
            model_field.related_model,
            depth=1,
            nesting_level=nesting_level + 1,
        )
    )

    embedded_field = EmbeddedFieldClass(
        serializer_class=cast(type[DynamicSerializer], serializer_class),
        # serializer_class=serializer_class,
        source=model_field.name,
    )
    # Attach the field schema so access rules can be applied here.
    embedded_field.field_schema = get_field_schema(model_field)

    camel_name = toCamelCase(model_field.name)
    serializer_part.add_embedded_field(camel_name, embedded_field)


def _through_serializer_factory(
    through_model: type[DynamicModel], m2m_field: models.ManyToManyField
) -> type[DynamicSerializer]:
    """Generate the DRF serializer class for a M2M model.

    :param through_model: the `through` model of the M2M relation.
    :param m2m_field: the ManyToMany field that describes the M2M relation
    :params target_field_name: the name of the M2M field in the source model

    This factory adds a field `target_field_name`. A field with this
    name is available on the through model. It is a FK pointing to the target.

    This FK field will lead to a HALTemporalHyperlinkedRelatedField on the
    through serializer. Because we do not want these field as subfields,
    the ThroughSerializer is merging the output of this field
    in its `to_representation` method.

    Furthermore, temporal fields are add to the through serializer
    if the target model is temporal.

    In the creation of the ThroughSerializer, a special attribute `target`
    is added to the `Meta` object. This is needed by the ThroughSerializer
    to be able to pick the right field for embedding into its output.
    """
    assert through_model == m2m_field.remote_field.through
    safe_dataset_id = to_snake_case(through_model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{through_model.__name__}_M2M"
    serializer_part = SerializerAssemblyLine(
        through_model,
        openapi_docs=(
            "The M2M table"
            f" for `{m2m_field.model.table_schema().name}.{toCamelCase(m2m_field.name)}`"
            f" that links to `{m2m_field.related_model.table_schema().name}`"
        ),
        target_field_name=m2m_field.name,
    )

    # The FK pointing to the target
    serializer_part.add_field_name(m2m_field.name)

    target_model = m2m_field.related_model
    if target_model.is_temporal():
        table_schema = target_model.table_schema()
        temporal: Temporal = cast(Temporal, table_schema.temporal)

        # The fields that define the boundaries of a particular related object are
        # added if they exist on the model.
        # (e.g. "beginGeldigheid" and "eindGeldigheid" for the "geldigOp" dimension
        # for GOB data)
        # NB. the `Temporal` dataclass return the boundary_fieldnames as snakecased!
        existing_fields_names = {f.name for f in through_model._meta.get_fields()}
        for dimension_fieldname, boundary_fieldnames in temporal.dimensions.items():
            for fn in boundary_fieldnames:
                snaked_fn = to_snake_case(fn)
                camel_fn = toCamelCase(fn)
                if snaked_fn in existing_fields_names:
                    serializer_part.add_field_name(camel_fn, source=snaked_fn)

    return serializer_part.construct_class(serializer_name, base_class=ThroughSerializer)


def _build_m2m_serializer(
    serializer_part: SerializerAssemblyLine,
    model: type[DynamicModel],
    m2m_field: models.ManyToManyField,
):
    """Add a serializer for a m2m field to the output parameters."""
    camel_name = toCamelCase(m2m_field.name)
    through_model = m2m_field.remote_field.through
    serializer_class = _through_serializer_factory(through_model, m2m_field)

    # Add the field to the serializer, but let it navigate to the through model
    # by using the reverse_name of it's first foreign key:
    source = to_snake_case(f"{through_model._meta.object_name}_through_{model.get_table_id()}")
    serializer_part.add_field(camel_name, serializer_class(source=source, many=True))


def _build_plain_serializer_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    """Add the field to the output parameters"""
    serializer_part.add_field_name(toCamelCase(model_field.name), source=model_field.name)


def _build_serializer_related_id_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    """Build the ``FIELD_id`` field for an related field."""
    camel_id_name = toCamelCase(model_field.attname)
    serializer_part.add_field_name(camel_id_name, source=model_field.attname)


def _build_serializer_loose_relation_id_field(
    serializer_part: SerializerAssemblyLine, model_field: LooseRelationField
):
    """Build the ``FIELD_id`` field for a loose relation."""
    camel_name = toCamelCase(model_field.name)
    loose_id_field_name = f"{camel_name}Id"
    serializer_part.add_field(loose_id_field_name, serializers.CharField(source=model_field.name))


def _build_serializer_blob_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field, field_schema: dict
):
    """Build the blob field"""
    camel_name = toCamelCase(model_field.name)
    serializer_part.add_field(
        camel_name,
        AzureBlobFileField(
            account_name=field_schema["account_name"],
            source=(model_field.name if model_field.name != camel_name else None),
        ),
    )


def _build_serializer_reverse_fk_field(
    serializer_part: SerializerAssemblyLine,
    model: type[DynamicModel],
    model_field: models.ManyToOneRel,
):
    """Build the ManyToOneRel field"""
    field_schema = get_field_schema(model_field)
    additional_relation = field_schema.reverse_relation
    if additional_relation is None:
        return

    att_name = model_field.name
    name = additional_relation.id
    format1 = additional_relation.format

    if format1 == "embedded":
        # Shows the identifiers of each item inline.
        view_name = "dynamic_api:{}-{}-detail".format(
            to_snake_case(model.get_dataset_id()),
            to_snake_case(model_field.related_model.table_schema().id),
        )
        serializer_part.add_field(
            name,
            HALTemporalHyperlinkedRelatedField(
                many=True,
                view_name=view_name,
                queryset=getattr(model, att_name),
            ),
        )
    elif format1 == "summary":
        # Only shows a count and href to the (potentially large) list of items.
        serializer_part.add_field(name, _RelatedSummaryField())
    else:
        logger.warning("Field %r uses unsupported format: %s", field_schema, format1)


def _generate_nested_relations(
    serializer_part: SerializerAssemblyLine, model: type[DynamicModel], nesting_level: int
):
    """Include fields that are implemented using nested tables."""
    schema_fields = {to_snake_case(f.name): f for f in model.table_schema().fields}
    for item in model._meta.related_objects:
        # Do not create fields for django-created relations.
        if item.name in schema_fields and schema_fields[item.name].is_nested_table:
            related_serializer = serializer_factory(
                item.related_model,
                nesting_level=nesting_level + 1,
            )

            serializer_part.add_field(item.name, related_serializer(many=True))
