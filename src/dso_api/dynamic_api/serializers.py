"""The data serialization for dynamic models.

The serializers in this package build on top of the :mod:`rest_framework_dso.serializers`,
to integrate the dynamic construction on top of the DSO serializer format.
Other application-specifice logic is also introduced here as well,
e.g. logic that depends on Amsterdam Schema policies. Such logic is *not* implemented
in the DSO base classes as those classes are completely generic.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Iterable, Optional, TypeVar, Union, cast
from urllib.parse import urlencode

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields import AutoFieldMixin
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import SimpleLazyObject, cached_property
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field, inline_serializer
from more_itertools import first
from rest_framework import serializers
from rest_framework.exceptions import ParseError
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.reverse import reverse
from rest_framework.serializers import Field
from rest_framework.utils.model_meta import RelationInfo
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
    HALLooseM2MUrlField,
    HALLooseRelationUrlField,
    TemporalHyperlinkedRelatedField,
    TemporalReadOnlyField,
)
from dso_api.dynamic_api.permissions import filter_unauthorized_expands
from dso_api.dynamic_api.temporal import (
    TemporalTableQuery,
    filter_temporal_m2m_slice,
    filter_temporal_slice,
)
from dso_api.dynamic_api.utils import get_source_model_fields, resolve_model_lookup
from rest_framework_dso.embedding import EmbeddedFieldMatch
from rest_framework_dso.fields import (
    AbstractEmbeddedField,
    DSORelatedLinkField,
    FieldsToDisplay,
    get_embedded_field_class,
)
from rest_framework_dso.serializers import (
    DSOModelListSerializer,
    DSOModelSerializer,
    HALLooseLinkSerializer,
)

MAX_EMBED_NESTING_LEVEL = 10
logger = logging.getLogger(__name__)

S = TypeVar("S", bound=serializers.Serializer)


@extend_schema_field(
    # Tell what this field will generate as object structure
    inline_serializer(
        "RelatedSummary",
        fields={
            "count": serializers.IntegerField(),
            "href": serializers.URLField(),
        },
    )
)
class RelatedSummaryField(Field):
    def to_representation(self, value: models.Manager):
        request = self.context["request"]
        url = reverse(get_view_name(value.model, "list"), request=request)

        # the "core_filters" attribute is available on all related managers
        filter_field = next(iter(value.core_filters.keys()))
        q_params = {toCamelCase(filter_field + "_id"): value.instance.pk}

        # If this is a temporal table, only return the appropriate records.
        if value.model.is_temporal():
            # The essence of filter_temporal_slice()
            query = TemporalTableQuery(request, value.model.table_schema())
            q_params.update(query.url_parameters)
            value = query.filter_queryset(value)

        query_string = ("&" if "?" in url else "?") + urlencode(q_params)
        return {"count": value.count(), "href": f"{url}{query_string}"}


class DynamicListSerializer(DSOModelListSerializer):
    """This serializer class is used internally when :class:`DynamicSerializer`
    is initialized with the ``many=True`` init kwarg to process a list of objects.
    """

    @cached_property
    def _m2m_through_fields(self) -> tuple[models.ForeignKey, models.ForeignKey]:
        """Give both foreignkeys that were part of this though table.
        The fields are ordered from the perspective of this serializer;
        with the first one being the field that was used to enter the through table,
        and the second to jump in the target relation.
        """
        target_model = self.child.Meta.model
        if not target_model.table_schema().through_table:
            raise RuntimeError("not an m2m table")

        first_fk = get_source_model_fields(self.parent, self.field_name, self)[-1].remote_field
        second_fk = first(
            (f for f in target_model._meta.get_fields() if f.is_relation and f is not first_fk)
        )
        return first_fk, second_fk

    def get_attribute(self, instance: DynamicModel):
        """Override list attribute retrieval for temporal filtering.
        The ``get_attribute`` call is made by DRF to retrieve the data from an instance,
        based on our ``source_attrs``.
        """
        value = super().get_attribute(instance)

        # When the source attribute of this object references the reverse_name field
        # (from a ForeignKey), the value is a RelatedManager subclass.
        if isinstance(value, models.Manager):
            request = self.context["request"]
            if value.model.is_temporal():
                # Make sure the target table is filtered by the temporal query,
                # instead of showing links to all records.
                value = filter_temporal_slice(request, value)

            if (
                value.model.table_schema().through_table
                and self._m2m_through_fields[1].related_model.is_temporal()
            ):
                # When this field lists the through table entries, also filter the target table.
                # Otherwise, the '_links' section shows all references from the M2M table, while
                # the embedding returns fewer entries because they are filtered temporal query.
                value = filter_temporal_m2m_slice(request, value, self._m2m_through_fields[1])

        return value

    def get_prefetch_lookups(self) -> list[Union[models.Prefetch, str]]:
        """Optimize M2M prefetch lookups to return correct temporal records only."""
        parent_model = self.child.Meta.model
        lookups = super().get_prefetch_lookups()
        request = self.context["request"]

        for i, lookup in enumerate(lookups):
            related_model, is_many = resolve_model_lookup(parent_model, lookup)
            if cast(DynamicModel, related_model).is_temporal() and is_many:

                # When the model is a temporal relationship, make sure the prefetch only returns
                # the proper temporal slice. The Prefetch objects allow adding these filters.
                lookups[i] = models.Prefetch(
                    lookup,
                    queryset=filter_temporal_slice(request, related_model.objects.all()),
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

    serializer_field_mapping = {
        **DSOModelSerializer.serializer_field_mapping,
        LooseRelationField: HALLooseRelationUrlField,
        LooseRelationManyToManyField: HALLooseRelationUrlField,
    }

    schema = serializers.SerializerMethodField()

    table_schema: DatasetTableSchema = None

    @cached_property
    def _request(self):
        """Get request from this or parent instance."""
        # Avoids resolving self.root all the time:
        return self.context["request"]

    def get_fields(self) -> dict[str, serializers.Field]:
        """Override DRF to remove fields that shouldn't be part of the response."""
        fields = {}
        for field_name, field in super().get_fields().items():
            if self._apply_permission(field_name, field):
                fields[field_name] = field

        return fields

    def _apply_permission(self, field_name: str, field: serializers.Field) -> bool:
        """Check permissions and apply any transforms."""
        user_scopes = self._request.user_scopes

        if field.source == "*":
            # e.g. _links field, always include. These sub serializers
            # do their own permission checks for their fields.
            return True

        # Find which ORM path is traversed for a field.
        # (typically one field, except when field.source has a dotted notation)
        model_fields = get_source_model_fields(self, field_name, field)
        for model_field in model_fields:
            field_schema = get_field_schema(model_field)

            # Check access
            permission = user_scopes.has_field_access(field_schema)
            if not permission:
                return False

            # Check transform from permission
            if transform_function := permission.transform_function():
                # Value must be transformed, decorate to_representation() for it.
                # Fields are a deepcopy, so this doesn't affect other serializer instances.
                # This strategy also avoids having to dig into the response data afterwards.
                field.to_representation = self._apply_transform(
                    field.to_representation, transform_function
                )

        return True

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
            self._request.user_scopes,
            expanded_fields=super().expanded_fields,
            skip_unauth=self.expand_scope.auto_expand_all,
        )

    @classmethod
    def get_embedded_field(cls, field_name, prefix="") -> AbstractEmbeddedField:
        """Overridden to improve error messages.
        At this layer, information about the Amsterdam schema
        can be used to provide a better error message.
        """
        try:
            return super().get_embedded_field(field_name, prefix=prefix)
        except ParseError:
            # Raise a better message, or fallback to the original message
            cls._raise_better_embed_error(field_name)
            raise

    @classmethod
    def _raise_better_embed_error(cls, field_name, prefix=""):
        """Improve the error message for embedded fields."""
        # Check whether there is a RelatedSummaryField for a link,
        # to tell that this field doesn't get expanded.
        try:
            link_field = cls._declared_fields["_links"]._declared_fields[field_name]
        except KeyError:
            return
        else:
            if isinstance(link_field, RelatedSummaryField):
                raise ParseError(
                    f"The field '{prefix}{field_name}' is not available"
                    f" for embedding as it's a summary of a huge listing."
                ) from None

    def get_embedded_objects_by_id(
        self, embedded_field: AbstractEmbeddedField, id_list: list[Union[str, int]]
    ) -> Union[models.QuerySet, Iterable[models.Model]]:
        """Retrieve a number of embedded objects by their identifier.

        This override makes sure the correct temporal slice is returned.
        """
        if embedded_field.is_loose:
            # Loose relations always point to a temporal object. In this case, the link happens on
            # the first key only, and the temporal slice makes sure that a second WHERE condition
            # happens on a temporal field (volgnummer/beginGeldigheid/..).
            # When 'identifier' is ["identificatie", "volgnummer"], take the first as grouper.
            model = embedded_field.related_model
            id_field = embedded_field.related_id_field or model.table_schema().identifier[0]
            return filter_temporal_slice(self._request, model.objects.all()).filter(
                **{f"{id_field}__in": id_list}
            )
        else:
            queryset = super().get_embedded_objects_by_id(embedded_field, id_list=id_list)

            # For all relations: if they are in fact temporal objects
            # still only return those that fit within the current timeframe.
            return filter_temporal_slice(self._request, queryset)

    @extend_schema_field(OpenApiTypes.URI)
    def get_schema(self, instance):
        """The schema field is exposed with every record"""
        table = instance.get_table_id()
        dataset_path = instance.get_dataset_path()
        return f"https://schemas.data.amsterdam.nl/datasets/{dataset_path}/dataset#{table}"

    def build_url_field(self, field_name, model_class):
        """Make the URL to 'self' is properly initialized."""
        if issubclass(self.serializer_url_field, serializers.Serializer):
            # Temporal serializer.
            field_kwargs = {"source": "*"}
        else:
            # Normal DSOSelfLinkField, link to correct URL.
            field_kwargs = {"view_name": get_view_name(model_class, "detail")}

        return self.serializer_url_field, field_kwargs

    def build_relational_field(self, field_name: str, relation_info: RelationInfo):
        """Make sure temporal links get a different field class."""
        field_class, field_kwargs = super().build_relational_field(field_name, relation_info)
        related_model = relation_info.related_model

        if "view_name" in field_kwargs:
            # Fix the view name to point to our views.
            field_kwargs["view_name"] = get_view_name(related_model, "detail")

        # Upgrade the field type when it's a link to a temporal model.
        if field_class is DSORelatedLinkField and related_model.table_schema().is_temporal:
            # Ideally this would just be an upgrade to a different field class.
            # However, since the "identificatie" and "volgnummer" fields are dynamic,
            # a serializer class is better suited as field type. That ensures the sub object
            # is properly generated in the OpenAPI spec as a distinct class type.
            field_class = _temporal_link_serializer_factory(relation_info.related_model)
            field_kwargs.pop("queryset", None)
            field_kwargs.pop("view_name", None)

        return field_class, field_kwargs

    def build_property_field(self, field_name, model_class):
        """This is called for the foreignkey_id fields.
        As the field name doesn't reference the model field directly,
        DRF assumes it's an "@property" on the model.
        """
        model_field = model_class._meta._forward_fields_map.get(field_name)
        if (
            model_field is not None
            and isinstance(model_field, models.ForeignKey)
            and model_field.related_model.is_temporal()
        ):
            return TemporalReadOnlyField, {}
        else:
            return super().build_property_field(field_name, model_class)


class DynamicBodySerializer(DynamicSerializer):
    """This subclass of the dynamic serializer only exposes the non-relational fields.

    Ideally, this should be obsolete as the serializer_factory() can avoid
    generating those fields in the first place.
    """

    def get_fields(self):
        """Remove fields that shouldn't be in the body."""
        fields = super().get_fields()

        # Remove fields from the _links field too. This is not done in the serializer
        # itself as that creates a cross-dependency between the parent/child.fields property.
        links_field = fields.get("_links")
        if links_field is not None and isinstance(links_field, DynamicLinksSerializer):
            if fields_to_display := self.fields_to_display:  # checks __bool__ for allow_all
                # The 'invalid_fields' is not checked against here, as that already happened
                # for the top-level fields reduction.
                main_and_links_fields = self.get_valid_field_names(fields)
                fields_to_keep, _ = fields_to_display.get_allow_list(main_and_links_fields)
                fields_to_keep.update(links_field.fields_always_included)
                links_field.fields = {
                    name: field
                    for name, field in links_field.fields.items()
                    if name in fields_to_keep
                }

        return fields

    def get_valid_field_names(self, fields: dict[str, serializers.Field]) -> set[str]:
        """Override to allow limiting the ``_links`` field layout too.
        By allowing the names from the ``_links`` field as if these exist at this level,
        those fields can be restricted quite naturally. This is needed to unclutter
        the ``_links`` output when nested relations are queried.
        """
        valid_names = super().get_valid_field_names(fields)

        # When the _links object is a serializer, also allow these fields
        # names as if these are present here.
        links_field = fields.get("_links")
        if links_field is not None and isinstance(links_field, DynamicLinksSerializer):
            links_field.parent = self  # perform early Field.bind()
            links_fields = set(links_field.fields.keys()) - links_field.fields_always_included
            valid_names.update(links_fields)

        return valid_names


class DynamicLinksSerializer(DynamicSerializer):
    """The serializer for the ``_links`` field.
    Following DSO/HAL guidelines, it contains "self", "schema", and all relational fields.
    """

    fields_always_included = {"self", "schema"}

    @property
    def fields_to_display(self):
        # Make sure child serializers (e.g. temporal relations / through serializers)
        # don't reduce their fields by taking this object from their "parent" serializer.
        return FieldsToDisplay()

    @property
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        # No need for our super class try look for expanded fields.
        return super().expanded_fields

    def limit_return_fields(self, fields):
        # Don't apply the ?_fields=... request here, let the parent to this instead.
        # Otherwise there is an initialization loop in get_fields() to find
        # the fields of the parent and child at the same time.
        return fields

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
            (
                serializers.ModelSerializer,
                serializers.ListSerializer,  # e.g. list of ModelSerializer
                serializers.RelatedField,
                serializers.ManyRelatedField,
            ),
        ):
            return False

        # Resolve the model field that this serializer field links to.
        # The source_attrs is generated here as it's created later in field.bind().
        model_fields = get_source_model_fields(self, name, field)
        for model_field in model_fields:
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
    It's fields are defined by the factory function, so little code is found here.
    """

    def limit_return_fields(self, fields):
        # Don't limit a through serializer via ?_fields=...,
        # as this exists in the _links section.
        return fields


_serializer_factory_cache = LRUCache(maxsize=100000)
_temporal_link_serializer_factory_cache = LRUCache(maxsize=100000)


def clear_serializer_factory_cache():
    _serializer_factory_cache.clear()
    _temporal_link_serializer_factory_cache.clear()


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: clear_serializer_factory_cache())


class SerializerAssemblyLine:
    """The intermediate result of the serializer factory"""

    def __init__(
        self,
        model: type[DynamicModel],
        fields=None,
        depth: int = 0,
        openapi_docs: str = "",
        factory_name: Optional[str] = None,
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
            "_factory_function": factory_name,
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

        if field.source == name:
            # Avoid errors only seen later when the actual view is called,
            # and it's impossible to find out where the field was created.
            raise RuntimeError("DRF will assert it's redundant to have source == field_name.")

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

    def construct_class(self, class_name, base_class: type[S]) -> type[S]:
        """Perform dynamic class construction"""
        return type(class_name, (base_class,), self.class_attrs)


def _serializer_cache_key(model, depth=0, nesting_level=0):
    """The cachetools allow definining the cache key,
    so the nesting level does not bypass the cache which it would with lru_cache().
    """
    return hashkey(model, depth)


@cached(cache=_serializer_factory_cache, key=_serializer_cache_key)
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
        model,
        depth=depth,
        openapi_docs=table_schema.get("description", table_schema.name),
        factory_name="serializer_factory",
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

    # TODO: Resolve the actual names of the fields in the database
    # by doing `table_schema.get_field_id(x).name for x in identifier`
    # then do the same when matching them below with the model_field name
    if table_schema.temporal:
        unwanted_identifiers = list(map(toCamelCase, table_schema.identifier))
    else:
        unwanted_identifiers = []

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        if model_field.auto_created and isinstance(model_field, AutoFieldMixin):
            # Don't want to render fields in the API which aren't part of the schema.
            continue

        field_camel_case = toCamelCase(model_field.name)
        field_schema = get_field_schema(model_field)

        # Exclusions:
        if (
            # Do not render PK and FK to parent on nested tables
            (model.has_parent_table() and model_field.name in ["id", "parent"])
            # Do not render temporal fields (e.g.: "volgnummer" and "identificatie").
            # Yet "id" / "pk" is still part of the main body.
            or (table_schema.temporal and field_camel_case in unwanted_identifiers)
            # Dont render intermediate keys (e.g. "relation_identificatie" / "relation_volgnummer")
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


def _links_serializer_factory(
    model: type[DynamicModel], depth: int
) -> type[DynamicLinksSerializer]:
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
        factory_name="_links_serializer_factory",
    )

    # Configure the serializer class to use for the link to 'self'
    if model.is_temporal():
        field_class = _temporal_link_serializer_factory(model)
        serializer_part.class_attrs["serializer_url_field"] = field_class
    else:
        field_class = _nontemporal_link_serializer_factory(model)
        serializer_part.class_attrs["serializer_url_field"] = field_class

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        # Only create fields for relations, avoid adding non-relation fields in _links.
        if isinstance(model_field, models.ManyToOneRel):
            _build_serializer_reverse_fk_field(serializer_part, model_field)
        # This includes LooseRelationManyToManyField
        elif isinstance(model_field, models.ManyToManyField):
            _build_m2m_serializer_field(serializer_part, model, model_field)
        elif isinstance(model_field, (RelatedField, ForeignObjectRel, LooseRelationField)):
            _build_serializer_links_field(serializer_part, model_field)

    # Generate serializer class
    return serializer_part.construct_class(serializer_name, base_class=DynamicLinksSerializer)


def _nontemporal_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[serializers.ModelSerializer]:
    """Construct a serializer that represents a relationship of which the remote
    table is not temporal."""
    if related_model.is_temporal():
        raise ValueError(f"Use {_temporal_link_serializer_factory.__name__} instead")

    table_schema = related_model.table_schema()
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the relationship to {table_schema.name}.",
        factory_name="_nontemporal_link_serializer_factory",
    )

    serializer_part.add_field("href", _build_href_field(related_model))
    if related_model.has_display_field():
        source = related_model.get_display_field()
        serializer_part.add_field(
            "title", serializers.CharField(source=source if source != "title" else None)
        )
    primary_id = first(table_schema.identifier)
    serializer_part.add_field_name(toCamelCase(primary_id), source=to_snake_case(primary_id))

    # Construct the class
    safe_dataset_id = to_snake_case(related_model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{related_model.__name__}LinkSerializer"
    return serializer_part.construct_class(serializer_name, serializers.ModelSerializer)


@cached(cache=_temporal_link_serializer_factory_cache)
def _temporal_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[serializers.ModelSerializer]:
    """Construct a serializer that represents a relationship in which the remote
    table is temporal.

    As the temporal field names are dynamic, a custom serializer is generated
    that has the exact field definition with the right field names.
    By having the whole layout defined once, it can be treated as a class type
    in the OpenAPI spec, and reduces runtime discovery of temporality.
    Other attempts (such as adding data in ``to_representation()``)
    can't be properly represented as an OpenAPI schema.

    For non-temporal fields, relations are best defined
    using the generic `DSORelatedLinkField` field.
    """
    if not related_model.is_temporal():
        raise ValueError(f"Use {_nontemporal_link_serializer_factory.__name__} in stead")

    table_schema = related_model.table_schema()
    temporal: Temporal = cast(Temporal, table_schema.temporal)
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the relationship to {table_schema.name}.",
        factory_name="_temporal_link_serializer_factory",
    )

    # Add the regular fields (same as non-temporal relations)
    serializer_part.add_field(
        "href",
        _build_href_field(
            related_model, field_cls=TemporalHyperlinkedRelatedField, table_schema=table_schema
        ),
    )
    if related_model.has_display_field():
        serializer_part.add_field(
            "title", serializers.CharField(source=related_model.get_display_field())
        )

    # Add the temporal fields, whose names depend on the schema
    temporal_id, primary_id = (
        table_schema.get_field_by_id(temporal.identifier).name,
        table_schema.get_field_by_id(first(table_schema.identifier)).name,
    )
    serializer_part.add_field_name(toCamelCase(temporal_id), source=to_snake_case(temporal_id))
    serializer_part.add_field_name(toCamelCase(primary_id), source=to_snake_case(primary_id))

    # Construct the class
    safe_dataset_id = to_snake_case(related_model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{related_model.__name__}LinkSerializer"
    return serializer_part.construct_class(serializer_name, serializers.ModelSerializer)


def _loose_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[HALLooseLinkSerializer]:
    """Construct a serializer that represents a loose relationship.

    At runtime, a loose relationship does not receive an object but a
    str, since LooseRelationField inherits from CharField.

    The primary id of the relation is used to contruct the href, title and id field.
    """
    table_schema = related_model.table_schema()
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the loose relationship to {table_schema.name}.",
        factory_name="_loose_link_serializer_factory",
    )
    serializer_part.add_field(
        "href",
        _build_href_field(related_model, field_cls=HALLooseRelationUrlField),
    )
    if related_model.has_display_field():
        serializer_part.add_field("title", serializers.CharField(source="*"))

    # Add the primary identifier, whose names depend on the schema
    primary_id = first(table_schema.identifier)
    serializer_part.add_field(toCamelCase(primary_id), serializers.CharField(source="*"))

    # Construct the class
    safe_dataset_id = to_snake_case(related_model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{related_model.__name__}LinkSerializer"
    serializer_part.class_attrs.pop("Meta")  # we dont need Meta on regular Serializers

    return serializer_part.construct_class(serializer_name, HALLooseLinkSerializer)


def _build_serializer_field(  # noqa: C901
    serializer_part: SerializerAssemblyLine, model_field: models.Field, nesting_level: int
):
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
        if additional_relation is not None and additional_relation.format != "summary":
            _build_serializer_embedded_field(serializer_part, model_field, nesting_level)
        return
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


def _through_serializer_factory(  # noqa: C901
    m2m_field: models.ManyToManyField,
) -> type[ThroughSerializer]:
    """Generate the DRF serializer class for a M2M model.

    This works directly on the database fields of the through model,
    so unnecessary retrievals of the related object are avoided.
    When the target model has temporal data, those attributes are also included.
    """
    through_model = m2m_field.remote_field.through
    target_model = m2m_field.related_model
    target_table_schema: DatasetTableSchema = m2m_field.related_model.table_schema()
    loose = isinstance(m2m_field, LooseRelationManyToManyField)

    try:
        # second foreign key of the through model
        target_fk_name = m2m_field.m2m_reverse_field_name()
    except AttributeError as e:
        # Adorn this exception with a clue about what we're trying to do.
        # This exception happened when the URLConf import causes an exception during
        # router initialization, which is silenced by runserver's autoreload code.
        # It ends up as an error here because at the next (re)import,
        # the M2M field is no longer able to match the models to it's foreign key instances,
        # showing the error:
        # "'ManyToManyField' object has no attribute '_m2m_reverse_name_cache'".

        # In Python 3.10, AttributeError has a name attribute, but we support 3.9.
        if "_m2m_reverse_name_cache" in str(e):
            raise AttributeError(f"{e} ({m2m_field})") from e
        else:
            raise

    # Start serializer construction.
    # The "href" field reads the target of the M2M table.
    serializer_part = SerializerAssemblyLine(
        through_model,
        openapi_docs=(
            "The M2M table"
            f" for `{m2m_field.model.table_schema().name}.{toCamelCase(m2m_field.name)}`"
            f" that links to `{target_table_schema.name}`"
        ),
        factory_name="_through_serializer_factory",
    )

    temporal: Optional[Temporal] = target_table_schema.temporal
    # Add the "href" link which directly reads the M2M foreign key ID.
    # This avoids having to retrieve any foreign object.
    href_field_cls = HyperlinkedRelatedField
    field_kwargs = {}
    if loose:
        href_field_cls = HALLooseM2MUrlField
    elif temporal is not None:
        href_field_cls = TemporalHyperlinkedRelatedField
        field_kwargs["table_schema"] = target_table_schema
    serializer_part.add_field(
        "href",
        _build_href_field(
            target_model,
            lookup_field=f"{target_fk_name}_id",
            lookup_url_kwarg="pk",
            field_cls=href_field_cls,
            **field_kwargs,
        ),
    )

    if temporal is None or loose:
        # Add the related identifier with its own name for regular M2M and LooseM2M
        # The implicit assumption here is that non-temporal tables never have compound keys
        # so that we always have the format <target_fk_name>_id in the through table
        # pointing to the remote side of the relation from the perspective of the ManyToManyField
        serializer_part.add_field(
            toCamelCase(
                target_table_schema.get_field_by_id(first(target_table_schema.identifier)).name
            ),
            serializers.CharField(source=f"{target_fk_name}_id", read_only=True),
        )

    if target_model.has_display_field():
        # Take the title directly from the linked model
        if target_model.get_display_field() == "id":
            title_field = f"{target_fk_name}_id"  # optimized by reading local version
        else:
            title_field = f"{target_fk_name}.{target_model.get_display_field()}"

        serializer_part.add_field(
            "title", serializers.CharField(source=title_field, read_only=True)
        )

    # See if the table has historical data
    if temporal is not None and not loose:
        # Include the temporal identifier of the targeted relationship,
        # as this is part of the existing fields of the M2M table.
        id_seq = first(target_table_schema.identifier)  # e.g.: "identificatie"
        serializer_part.add_field_name(id_seq, source=f"{target_fk_name}_{id_seq}")
        id_field = temporal.identifier  # e.g.: "volgnummer"
        serializer_part.add_field_name(id_field, source=f"{target_fk_name}_{id_field}")

        # The fields that define the boundaries of a particular related object are
        # added if they exist on the model.
        # (e.g. "beginGeldigheid" and "eindGeldigheid" for the "geldigOp" dimension
        # for GOB data)
        # NB. the `Temporal` dataclass return the boundary_fieldnames as snakecased!
        existing_fields_names = {f.name for f in through_model._meta.get_fields()}
        for dimension_fieldname, boundary_fieldnames in temporal.dimensions.items():
            for dim_field in boundary_fieldnames:
                snaked_fn = to_snake_case(dim_field)
                if snaked_fn in existing_fields_names:  # TODO: still need this?
                    serializer_part.add_field_name(toCamelCase(dim_field), source=snaked_fn)

    # Finalize as serializer
    safe_dataset_id = to_snake_case(through_model.get_dataset_id())
    serializer_name = f"{safe_dataset_id.title()}{toCamelCase(through_model.__name__)}_M2M"
    return serializer_part.construct_class(serializer_name, base_class=ThroughSerializer)


def _build_m2m_serializer_field(
    serializer_part: SerializerAssemblyLine,
    model: type[DynamicModel],
    m2m_field: models.ManyToManyField,
):
    """Add a serializer for a m2m field to the output parameters.

    Instead of jumping over the M2M field through the ManyToMany field relation,
    the reverse name of it's first ForeignKey is used to step into the M2M table itself.
    (Django defines the first ForeignKey to always be the one that points to the model
    declaring the ManyToManyField).

    This allows exposing the intermediate table and it's (temporal) data. It also avoids
    unnecessary queries joining both the through and target table.
    """
    camel_name = toCamelCase(m2m_field.name)
    serializer_class = _through_serializer_factory(m2m_field)

    # Add the field to the serializer, but let it navigate to the through model
    # by using the reverse_name of it's first foreign key:
    source = m2m_field.get_path_info()[0].join_field.name
    serializer_part.add_field(camel_name, serializer_class(source=source, many=True))


def _build_plain_serializer_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    """Add the field to the output parameters by name
    and let Serializer.serializer_mapping determine
    which fieldclass will be used for the representation."""
    serializer_part.add_field_name(toCamelCase(model_field.name), source=model_field.name)


def _build_serializer_links_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    related_model = model_field.related_model

    if isinstance(model_field, LooseRelationField):
        field_class = _loose_link_serializer_factory(related_model)
    elif model_field.related_model.table_schema().is_temporal:
        field_class = _temporal_link_serializer_factory(related_model)
    else:
        field_class = _nontemporal_link_serializer_factory(related_model)

    field_kwargs = {}
    field_name = toCamelCase(model_field.name)
    if field_name != model_field.name:
        # DRF errors out if source is equal to field name
        field_kwargs["source"] = model_field.name

    if model_field.many_to_many:
        field_kwargs["many"] = True

    serializer_part.add_field(
        toCamelCase(model_field.name),
        field_class(**field_kwargs),
    )


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
    model_field: models.ManyToOneRel,
):
    """Build the ManyToOneRel field"""
    field_schema = get_field_schema(model_field)
    additional_relation = field_schema.reverse_relation
    if additional_relation is None:
        return

    name = additional_relation.id
    format1 = additional_relation.format

    if format1 == "embedded":
        # Shows the identifiers of each item inline.
        target_model: type[DynamicModel] = model_field.related_model
        if target_model.is_temporal():
            # Since the "identificatie" / "volgnummer" fields are dynamic, there is no good
            # way to generate an OpenAPI definition from this unless the whole result
            # is defined as a serializer class that has those particular fields.
            field_class = _temporal_link_serializer_factory(target_model)
        else:
            field_class = _nontemporal_link_serializer_factory(target_model)

        serializer_part.add_field(name, field_class(read_only=True, many=True))
    elif format1 == "summary":
        # Only shows a count and href to the (potentially large) list of items.
        serializer_part.add_field(name, RelatedSummaryField())
    else:
        logger.warning("Field %r uses unsupported format: %s", field_schema, format1)


def _build_href_field(
    target_model: type[DynamicModel],
    lookup_field: str = "pk",
    field_cls=HyperlinkedRelatedField,
    **kwargs,
) -> HyperlinkedRelatedField:
    """Generate a link field for a regular, temporal or loose relation.
    Use the 'lookup_field' argument to change the source of the hyperlink ID.
    """
    href_kwargs = dict(
        view_name=get_view_name(target_model, "detail"),
        read_only=True,  # avoids having to add a queryset
        source="*",  # reads whole object, but only takes 'lookup_field' for the ID.
        lookup_field=lookup_field,
        **kwargs,
    )
    return field_cls(**href_kwargs)


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
