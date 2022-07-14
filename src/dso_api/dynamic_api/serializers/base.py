"""The data serialization for dynamic models.

The serializers define how the output is rendered.
Its "tree of fields" match exactly how the output will be rendered.
These base classes provide all the runtime logic such as:

* expanding fields
* limiting which fields the user may access.
* filtering temporal records.

A huge part of this logic is build on top of the :mod:`rest_framework_dso.serializers`,
which provides the generic logic and standards adherence to the DSO-specification.

So this extra layer does two things: it combines policies from "Amsterdam Schema"
(which is not found in :mod:`rest_framework_dso`), and it does
application/domain-specific logic such as temporal field handling.

Note these classes are all *base* classes.
The call to `:func:`~dso_api.dynamic_api.serializers.serializer_factory`
constructs the derived classes for each dataset.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Iterable, Union, cast

from django.db import models
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from more_itertools import first
from rest_framework import serializers
from rest_framework.exceptions import ParseError
from rest_framework.utils.model_meta import RelationInfo
from schematools.contrib.django.models import (
    DynamicModel,
    LooseRelationField,
    LooseRelationManyToManyField,
)
from schematools.types import DatasetTableSchema, Json

from dso_api.dynamic_api.permissions import filter_unauthorized_expands
from dso_api.dynamic_api.temporal import filter_temporal_m2m_slice, filter_temporal_slice
from dso_api.dynamic_api.utils import (
    get_serializer_source_fields,
    get_source_model_fields,
    get_view_name,
    resolve_model_lookup,
)
from rest_framework_dso.embedding import EmbeddedFieldMatch
from rest_framework_dso.fields import AbstractEmbeddedField, DSORelatedLinkField, FieldsToDisplay
from rest_framework_dso.serializers import DSOModelListSerializer, DSOModelSerializer
from rest_framework_dso.utils import get_serializer_relation_lookups

from . import fields

logger = logging.getLogger(__name__)


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
                value = filter_temporal_slice(request, value.all())

            if (
                value.model.table_schema().through_table
                and self._m2m_through_fields[1].related_model.is_temporal()
            ):
                # When this field lists the through table entries, also filter the target table.
                # Otherwise, the '_links' section shows all references from the M2M table, while
                # the embedding returns fewer entries because they are filtered temporal query.
                value = filter_temporal_m2m_slice(
                    request, value.all(), self._m2m_through_fields[1]
                )

        return value

    def get_queryset_iterator(self, queryset: models.QuerySet) -> Iterable[models.Model]:
        """Optimize querysets to access only the fields our serializer needs.

        This checks which model fields "self.fields" will access, and limits the
        queryset accordingly. In effect, this reduces field access when "?_fields=..." is used
        on the request, and it avoids requesting database fields that the user has no access to.
        """
        only_fields = get_serializer_source_fields(self)
        if only_fields:
            # Make sure no unnecessary fields are requested from the database.
            # This avoids accessing privileged data, and reduces bandwidth for ?_fields=.. queries.
            queryset = queryset.only(*only_fields)

        return super().get_queryset_iterator(queryset)

    def get_prefetch_lookups(self) -> list[Union[models.Prefetch, str]]:
        """Optimize prefetch lookups

        - Return correct temporal records only (for M2M tables).
        - Make sure prefetches only read the subset of user-accessible fields.
        """
        relation_lookups = get_serializer_relation_lookups(self)

        lookups = []
        for lookup, field in relation_lookups.items():
            if lookup.startswith("rev_m2m_"):
                # The reverse m2m lookups don't seem to benefit from prefetch related:
                continue

            # The prefetch object get a custom queryset, so unwanted rows/fields are excluded.
            prefetch_queryset = self._get_prefetch_queryset(lookup, field)
            lookups.append(models.Prefetch(lookup, queryset=prefetch_queryset))

        return lookups

    def _get_prefetch_queryset(self, lookup: str, field: serializers.Field) -> models.QuerySet:
        """Construct a queryset for a prefetch on the ORM path lookup path.
        The serializer field is passed as well, to detect which source fields it might need.
        """
        # Find which model fields the relation would traverse.
        # This information is not available on serializer field objects (nor can't be)
        parent_model = self.child.Meta.model
        model_field = resolve_model_lookup(parent_model, lookup)[-1]

        # Avoid prefetching unnecessary fields from the database.
        only_fields = self._get_prefetch_fields(field, model_field)
        prefetch_queryset = model_field.related_model.objects.only(*only_fields)

        # Avoid prefetching unnecessary temporal records for M2M relations
        # (that is, records that not part of the current temporal slice).
        if cast(DynamicModel, model_field.related_model).is_temporal() and (
            # Tell whether the field returns many results (e.g. M2M).
            model_field.many_to_many
            or model_field.one_to_many
        ):
            request = self.context["request"]
            prefetch_queryset = filter_temporal_slice(request, prefetch_queryset)

        return prefetch_queryset

    def _get_prefetch_fields(
        self,
        field: serializers.Field,
        model_field: RelatedField | ForeignObjectRel | LooseRelationField,
    ) -> list[str]:
        """Tell which fields the prefetch query should retrieve."""
        if isinstance(field, serializers.BaseSerializer):
            only_fields = get_serializer_source_fields(field)
            if isinstance(model_field, models.ManyToOneRel):  # A reverse FK (ManyToOneRel)
                # For reverse relations, the reverse foreign key needs to be provided too.
                # Otherwise, our call to prefetch_related_objects() fails on deferred attributes.
                only_fields.append(model_field.field.attname)
            return only_fields
        else:
            raise NotImplementedError(f"Can't determine reduced fields subset yet for: {field}")

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
        LooseRelationField: fields.HALLooseRelationUrlField,
        LooseRelationManyToManyField: fields.HALLooseRelationUrlField,
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
            field_schema = DynamicModel.get_field_schema(model_field)

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
            if isinstance(link_field, fields.RelatedSummaryField):
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
        """Factory logic - Make the URL to 'self' is properly initialized."""
        if issubclass(self.serializer_url_field, serializers.Serializer):
            # Temporal serializer.
            field_kwargs = {"source": "*"}
        else:
            # Normal DSOSelfLinkField, link to correct URL.
            field_kwargs = {"view_name": get_view_name(model_class, "detail")}

        return self.serializer_url_field, field_kwargs

    def build_relational_field(self, field_name: str, relation_info: RelationInfo):
        """Factory logic - This makes sure temporal links get a different field class."""
        field_class, field_kwargs = super().build_relational_field(field_name, relation_info)
        related_model = relation_info.related_model

        if "view_name" in field_kwargs:
            # Fix the view name to point to our views.
            field_kwargs["view_name"] = get_view_name(related_model, "detail")

        # Upgrade the field type when it's a link to a temporal model.
        if field_class is DSORelatedLinkField and related_model.table_schema().is_temporal:
            from dso_api.dynamic_api.serializers.factories import _temporal_link_serializer_factory

            # Ideally this would just be an upgrade to a different field class.
            # However, since the "identificatie" and "volgnummer" fields are dynamic,
            # a serializer class is better suited as field type. That ensures the sub object
            # is properly generated in the OpenAPI spec as a distinct class type.
            field_class = _temporal_link_serializer_factory(relation_info.related_model)
            field_kwargs.pop("queryset", None)
            field_kwargs.pop("view_name", None)

        return field_class, field_kwargs

    def build_property_field(self, field_name, model_class):
        """Factory logic - This is called for the foreignkey_id fields.
        As the field name doesn't reference the model field directly,
        DRF assumes it's an "@property" on the model.
        """
        model_field = model_class._meta._forward_fields_map.get(field_name)
        if (
            model_field is not None
            and isinstance(model_field, models.ForeignKey)
            and model_field.related_model.is_temporal()
        ):
            return fields.TemporalReadOnlyField, {}
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
            if self.fields_to_display.reduced():
                # The 'invalid_fields' is not checked against here, as that already happened
                # for the top-level fields reduction.
                main_and_links_fields = self.get_valid_field_names(fields)
                fields_to_keep, _ = self.fields_to_display.get_allow_list(main_and_links_fields)
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


class ThroughSerializer(DynamicSerializer):
    """The serializer for the through table of M2M relations.
    It's fields are defined by the factory function, so little code is found here.
    """

    def limit_return_fields(self, fields):
        # Don't limit a through serializer via ?_fields=...,
        # as this exists in the _links section.
        return fields
