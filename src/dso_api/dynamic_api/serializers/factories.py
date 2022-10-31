"""Serializer factories

This module constructs the serializer *classes* for each dataset.
Note this doesn't do anything with the *request* object as the whole purpose
of this module is to construct the complete serializer "field-tree" once at startup.

The main function is :func:`serializer_factory`, and everything else starts from there.
The `_links` object for instance, is backed by another serializer class, and so
are the individual elements in that section. These elements are all serializer objects.

By making everything a serializer object (instead of fields that return random dicts),
the OpenAPI logic can generate a complete definition of the expected output.
This allows clients (e.g. dataportaal) to generate a lovely JavaScript client based on
the OpenAPI specification.

When a request is received, these serializer class is instantiated into
an object (in the view). The serializer *object* will also strip some fields
that the user doesn't have access to. DRF supports that by making a deepcopy
of the declared fields, so per-request changes don't affect the static class.
"""
from __future__ import annotations

import logging
from typing import Optional, TypeVar, cast

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.fields import AutoFieldMixin
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import SimpleLazyObject
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from schematools.contrib.django.factories import is_dangling_model
from schematools.contrib.django.models import (
    DynamicModel,
    LooseRelationField,
    LooseRelationManyToManyField,
)
from schematools.contrib.django.signals import dynamic_models_removed
from schematools.naming import to_snake_case, toCamelCase
from schematools.types import DatasetFieldSchema, DatasetTableSchema, Temporal

from dso_api.dynamic_api.utils import get_view_name
from rest_framework_dso.fields import AbstractEmbeddedField, get_embedded_field_class
from rest_framework_dso.serializers import HALLooseLinkSerializer

from . import base, fields
from .base import LinkSerializer

MAX_EMBED_NESTING_LEVEL = 10
S = TypeVar("S", bound=serializers.Serializer)

logger = logging.getLogger(__name__)
_serializer_factory_cache = LRUCache(maxsize=100000)
_temporal_link_serializer_factory_cache = LRUCache(maxsize=100000)


EXPOSED_SHORTNAMES = {
    # Datasets that used shortnames, which we've accidentally exposed instead of the actual names.
    # By limiting the compatibility check to this list, new datasets won't get the compat fields.
    # After all, they don't need to transition their API clients.
    "brk",
    "loopfietsnetwerk",
    "standbedrijven",
    "standvastgoed",
    # No data in PRD: "handelsregister",
    # Not used PRD: "objectenopenbareruimte",
}


def _needs_shortname_compatibility(
    field_schema: DatasetFieldSchema, model_field: models.Field | ForeignObjectRel
):
    """Tell whether the field needs to provide backwards compatibility.
    We've accidentally exposed shortnames in the API.
    TODO: This feature should be removed after clients migrated.
    """
    return (
        field_schema.has_shortname
        and field_schema.table.dataset.id in EXPOSED_SHORTNAMES
        and isinstance(model_field, models.Field)  # forward relation
    )


def clear_serializer_factory_cache():
    _serializer_factory_cache.clear()
    _temporal_link_serializer_factory_cache.clear()


# When models are removed, clear the cache.
dynamic_models_removed.connect(lambda **kwargs: clear_serializer_factory_cache())


class SerializerAssemblyLine:
    """The intermediate result of the serializer factory.

    .. tip:
        If you want to debug this code, consider comparing the output of
        ``manage.py dump_serializers [--format={python,nested}] [applabel ...]``.
        This will reveal how the serializer layout will be created
    """

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
        dataset_schema = model.get_dataset_schema()
        self.class_attrs = {
            "__module__": f"dso_api.dynamic_api.serializers.{dataset_schema.python_name}",
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
) -> type[base.DynamicSerializer]:
    """Generate the DRF serializer class for a specific dataset model.

    Internally, this creates all serializer fields based on the metadata
    from the model, and underlying schema definition. It also generates
    a secondary serializer for the ``_links`` field where all relations are exposed.

    In short, this factory does in-memory would you'd typically write as:

    .. code-block:: python

        class SomeDatasetTableSerializer(DynamicSerializer):
            _links = SomeDatasetTableLinksSerializer(source="*")
            field1 = serializers.CharField(...)
            field2 = serializers.WhateverField(...)

            class Meta:
                model = SomeDatasetTable
                fields = ("_links", "field1", "field2")

    ...and all child fields are statically defined on the instance whenever possible.

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
    dataset_schema = model.get_dataset_schema()
    serializer_name = f"{dataset_schema.python_name}{model.__name__}Serializer"
    table_schema = model.table_schema()

    # Start the assemblage of the serializer
    serializer_part = SerializerAssemblyLine(
        model,
        depth=depth,
        openapi_docs=table_schema.get("description", table_schema.id),
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

    unwanted_identifiers = table_schema.identifier if table_schema.temporal else []

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        if model_field.auto_created and isinstance(model_field, AutoFieldMixin):
            # Don't want to render fields in the API which aren't part of the schema.
            continue

        field_schema = DynamicModel.get_field_schema(model_field)

        # Exclusions:
        if (
            # Do not render PK and FK to parent on nested tables
            (model.has_parent_table() and model_field.name in ["id", "parent"])
            # Do not render temporal fields (e.g.: "volgnummer" and "identificatie").
            # Yet "id" / "pk" is still part of the main body.
            or (table_schema.temporal and field_schema.id in unwanted_identifiers)
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
    return serializer_part.construct_class(serializer_name, base_class=base.DynamicBodySerializer)


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
) -> type[base.DynamicLinksSerializer]:
    """Generate the DRF serializer class for the ``_links`` section."""
    dataset_schema = model.get_dataset_schema()
    table_schema = model.table_schema()
    serializer_name = f"{dataset_schema.python_name}{table_schema.python_name}LinksSerializer"

    serializer_part = SerializerAssemblyLine(
        model,
        fields=["schema", "self"],
        openapi_docs=(
            f"The contents of the `{model.table_schema().id}._links` field."
            " It contains all relationships with objects."
        ),
        depth=depth,
        factory_name="_links_serializer_factory",
    )

    # Configure the serializer class to use for the link to 'self'
    # The 'fields_always_included' is set, so the 'self' link never hides fields.
    if model.is_temporal():
        self_link_class = _temporal_link_serializer_factory(model)
    else:
        self_link_class = _nontemporal_link_serializer_factory(model)
    self_link_class.fields_always_included = set(self_link_class.Meta.fields)
    serializer_part.class_attrs["serializer_url_field"] = self_link_class

    # Parse fields for serializer
    for model_field in model._meta.get_fields():
        # Only create fields for relations, avoid adding non-relation fields in _links.
        if isinstance(model_field, models.ManyToOneRel):
            _build_serializer_reverse_fk_field(serializer_part, model_field)
        # This includes LooseRelationManyToManyField
        elif isinstance(model_field, models.ManyToManyField):
            _build_m2m_serializer_field(serializer_part, model_field)
        elif isinstance(model_field, (RelatedField, ForeignObjectRel)):
            _build_link_serializer_field(serializer_part, model_field)

    # Generate serializer class
    return serializer_part.construct_class(serializer_name, base_class=base.DynamicLinksSerializer)


def _nontemporal_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[LinkSerializer]:
    """Construct a serializer that represents a relationship of which the remote
    table is not temporal."""
    if related_model.is_temporal():
        raise ValueError(f"Use {_temporal_link_serializer_factory.__name__} instead")

    table_schema = related_model.table_schema()
    dataset_schema = table_schema.dataset
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the relationship to {table_schema.id}.",
        factory_name="_nontemporal_link_serializer_factory",
    )

    serializer_part.add_field("href", _build_href_field(related_model))
    if related_model.has_display_field():
        source = related_model.get_display_field()
        serializer_part.add_field(
            "title", serializers.CharField(source=source if source != "title" else None)
        )

    primary_field = table_schema.identifier_fields[0]
    serializer_part.add_field_name(primary_field.name, source=primary_field.python_name)

    # Construct the class
    serializer_name = f"{dataset_schema.python_name}{related_model.__name__}LinkSerializer"
    return serializer_part.construct_class(serializer_name, base_class=LinkSerializer)


@cached(cache=_temporal_link_serializer_factory_cache)
def _temporal_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[LinkSerializer]:
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
    dataset_schema = table_schema.dataset
    temporal: Temporal = cast(Temporal, table_schema.temporal)
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the relationship to {table_schema.id}.",
        factory_name="_temporal_link_serializer_factory",
    )

    # Add the regular fields (same as non-temporal relations)
    serializer_part.add_field(
        "href",
        _build_href_field(
            related_model,
            field_cls=fields.TemporalHyperlinkedRelatedField,
            table_schema=table_schema,
        ),
    )
    if related_model.has_display_field():
        serializer_part.add_field(
            "title", serializers.CharField(source=related_model.get_display_field())
        )

    # Add the temporal fields, whose names depend on the schema
    primary_field = table_schema.identifier_fields[0]
    sequence_field = temporal.identifier_field
    serializer_part.add_field_name(primary_field.name, source=primary_field.python_name)
    serializer_part.add_field_name(sequence_field.name, source=sequence_field.python_name)

    # Construct the class
    serializer_name = f"{dataset_schema.python_name}{table_schema.python_name}LinkSerializer"
    return serializer_part.construct_class(serializer_name, base_class=LinkSerializer)


def _loose_link_serializer_factory(
    related_model: type[DynamicModel],
) -> type[HALLooseLinkSerializer]:
    """Construct a serializer that represents a loose relationship.

    At runtime, a loose relationship does not receive an object but a
    str, since LooseRelationField inherits from CharField.

    The primary id of the relation is used to construct the href, title and id field.
    """
    table_schema = related_model.table_schema()
    dataset_schema = table_schema.dataset
    serializer_part = SerializerAssemblyLine(
        model=related_model,
        openapi_docs=f"The identifier of the loose relationship to {table_schema.id}.",
        factory_name="_loose_link_serializer_factory",
    )
    serializer_part.add_field(
        "href",
        _build_href_field(related_model, field_cls=fields.HALLooseRelationUrlField),
    )
    if related_model.has_display_field():
        # Using source="*" because the source is already a str.
        serializer_part.add_field("title", serializers.CharField(source="*"))

    # Add the primary identifier, whose names depend on the schema
    primary_field = table_schema.identifier_fields[0]
    serializer_part.add_field(primary_field.name, serializers.CharField(source="*"))

    # Construct the class
    serializer_name = f"{dataset_schema.python_name}{table_schema.python_name}LooseLinkSerializer"
    serializer_part.class_attrs.pop("Meta")  # we dont need Meta on regular Serializers

    return serializer_part.construct_class(serializer_name, base_class=HALLooseLinkSerializer)


def _build_serializer_field(  # noqa: C901
    serializer_part: SerializerAssemblyLine, model_field: models.Field, nesting_level: int
):
    """Build a serializer field, results are written in 'output' parameters"""
    # Add extra embedded part for related fields
    # For NM relations, we need another type of EmbeddedField
    if isinstance(
        model_field, (models.ForeignKey, models.ManyToManyField, LooseRelationManyToManyField)
    ):
        # Embedded relations are only added to the main serializer.
        _build_serializer_embedded_field(serializer_part, model_field, nesting_level)

        if isinstance(model_field, models.ForeignKey):
            # Forward relation, or loose relation, add an id field in the main body.
            _build_serializer_related_id_field(serializer_part, model_field)
        return
    elif isinstance(model_field, ForeignObjectRel):
        # Reverse relations, are only added as embedded field when there is an explicit declaration
        field_schema = DynamicModel.get_field_schema(model_field)
        additional_relation = field_schema.reverse_relation
        if additional_relation is not None and additional_relation.format != "summary":
            _build_serializer_embedded_field(serializer_part, model_field, nesting_level)
        return

    if model_field.is_relation:
        return

    # Regular fields for the body, and some relation fields
    _build_plain_serializer_field(serializer_part, model_field)


def _build_serializer_embedded_field(
    serializer_part: SerializerAssemblyLine,
    model_field: RelatedField | ForeignObjectRel,
    nesting_level: int,
):
    """Build a embedded field for the serializer"""
    field_schema = DynamicModel.get_field_schema(model_field)
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
        serializer_class=cast(type[base.DynamicSerializer], serializer_class),
        # serializer_class=serializer_class,
        source=model_field.name,
    )
    # Attach the field schema so access rules can be applied here.
    embedded_field.field_schema = field_schema

    # The field name is still generated from the model_field, in case this is a reverse field.
    serializer_part.add_embedded_field(toCamelCase(model_field.name), embedded_field)

    # TODO: Temp. For backwards compatibility with accidentally exposed shortnames.
    if _needs_shortname_compatibility(field_schema, model_field):
        logger.debug("Adding shortname compat for embedding %s", field_schema)
        serializer_part.add_embedded_field(toCamelCase(field_schema.shortname), embedded_field)


def _through_serializer_factory(  # noqa: C901
    m2m_field: models.ManyToManyField,
) -> type[base.ThroughSerializer]:
    """Generate the DRF serializer class for a M2M model.

    This works directly on the database fields of the through model,
    so unnecessary retrievals of the related object are avoided.
    When the target model has temporal data, those attributes are also included.
    """
    through_model = m2m_field.remote_field.through
    target_model = m2m_field.related_model
    source_table_schema: DatasetTableSchema = m2m_field.model.table_schema()
    target_table_schema: DatasetTableSchema = m2m_field.related_model.table_schema()
    m2m_field_schema = DynamicModel.get_field_schema(m2m_field)
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
        if "_m2m_reverse_name_cache" in str(e) or "_meta" in str(e):
            raise AttributeError(f"{e} ({m2m_field})") from e
        else:
            raise

    # Start serializer construction.
    # The "href" field reads the target of the M2M table.
    serializer_part = SerializerAssemblyLine(
        through_model,
        openapi_docs=(
            "The M2M table"
            f" for `{source_table_schema.python_name}.{m2m_field_schema.name}`"
            f" that links to `{target_table_schema.python_name}`"
        ),
        factory_name="_through_serializer_factory",
    )

    temporal: Optional[Temporal] = target_table_schema.temporal
    # Add the "href" link which directly reads the M2M foreign key ID.
    # This avoids having to retrieve any foreign object.
    href_field_cls = HyperlinkedRelatedField
    field_kwargs = {}
    if loose:
        href_field_cls = fields.HALLooseM2MUrlField
    elif temporal is not None:
        href_field_cls = fields.TemporalHyperlinkedRelatedField
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
            target_table_schema.identifier_fields[0].name,
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
        # and read this is part from the existing fields of the M2M table (no extra JOIN needed).
        id_field = target_table_schema.identifier_fields[0]  # e.g. "identificatie"
        seq_field = temporal.identifier_field  # e.g. "volgnummer"
        serializer_part.add_field_name(
            id_field.name, source=f"{target_fk_name}_{id_field.python_name}"
        )
        serializer_part.add_field_name(
            seq_field.name, source=f"{target_fk_name}_{seq_field.python_name}"
        )

        # The fields that define the boundaries of a particular related object are
        # added if they exist on the model.
        # (e.g. "beginGeldigheid" and "eindGeldigheid" for the "geldigOp" dimension for GOB data)
        existing_fields_names = {f.name for f in through_model._meta.get_fields()}
        for dimension_name, boundary_fields in temporal.dimensions.items():
            for dim_field in boundary_fields:
                if dim_field.python_name in existing_fields_names:  # TODO: still need this?
                    serializer_part.add_field_name(dim_field.name, source=dim_field.python_name)

    # Finalize as serializer
    dataset = source_table_schema.dataset
    serializer_name = f"{dataset.python_name}{toCamelCase(through_model.__name__)}_M2M"
    return serializer_part.construct_class(serializer_name, base_class=base.ThroughSerializer)


def _build_m2m_serializer_field(
    serializer_part: SerializerAssemblyLine, m2m_field: models.ManyToManyField
):
    """Add a serializer for a m2m field to the output parameters.

    Instead of jumping over the M2M field through the ManyToMany field relation,
    the reverse name of it's first ForeignKey is used to step into the M2M table itself.
    (Django defines the first ForeignKey to always be the one that points to the model
    declaring the ManyToManyField).

    This allows exposing the intermediate table and it's (temporal) data. It also avoids
    unnecessary queries joining both the through and target table.
    """
    field_schema = DynamicModel.get_field_schema(m2m_field)
    serializer_class = _through_serializer_factory(m2m_field)

    # Add the field to the serializer, but let it navigate to the through model
    # by using the reverse_name of it's first foreign key:
    source = m2m_field.get_path_info()[0].join_field.name
    serializer_part.add_field(field_schema.name, serializer_class(source=source, many=True))

    # TODO: temp compat for brk.kadastraleobjecten.heeftEenRelatieMetVerblijfsobject
    if _needs_shortname_compatibility(field_schema, m2m_field):
        logger.debug("Adding shortname compat for M2M %s", field_schema)
        serializer_part.add_field(
            toCamelCase(field_schema.shortname), serializer_class(source=source, many=True)
        )


def _build_plain_serializer_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    """Add the field to the output parameters by name
    and let Serializer.serializer_mapping determine
    which fieldclass will be used for the representation."""
    field_schema = DynamicModel.get_field_schema(model_field)
    serializer_part.add_field_name(field_schema.name, source=model_field.name)

    # TODO: Temp. For backwards compatibility with accidentally exposing shortnames:
    if _needs_shortname_compatibility(field_schema, model_field):
        logger.debug("Adding shortname compat for field %s", field_schema)
        serializer_part.add_field_name(
            toCamelCase(field_schema.shortname), source=model_field.name
        )


def _build_link_serializer_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field | models.ForeignObjectRel
):
    """Build a field that will be an item in the ``_links`` section."""
    related_model = model_field.related_model
    field_kwargs = {}
    camel_name = toCamelCase(model_field.name)
    if camel_name != model_field.name:
        # DRF errors out if source is equal to field name
        field_kwargs["source"] = to_snake_case(model_field.name)

    if model_field.many_to_many:
        field_kwargs["many"] = True

    # The link element itself is constructed using a serializer instead of some simple field,
    # because this provides a proper field definition for the generated OpenAPI spec.
    if isinstance(model_field, LooseRelationField):
        field_class = _loose_link_serializer_factory(related_model)
        field_kwargs["source"] = model_field.attname  # receives ID value, not full object.
    elif model_field.related_model.table_schema().is_temporal:
        field_class = _temporal_link_serializer_factory(related_model)
    else:
        field_class = _nontemporal_link_serializer_factory(related_model)

    serializer_part.add_field(
        camel_name,  # Can be reverse relation, so based on model name.
        field_class(**field_kwargs),
    )

    # TODO: Temp. For backwards compatibility with accidentally exposing shortnames:
    field_schema = DynamicModel.get_field_schema(model_field)
    if _needs_shortname_compatibility(field_schema, model_field):
        logger.debug("Adding shortname compat for relation %s", field_schema)
        field_kwargs.setdefault("source", model_field.name)
        serializer_part.add_field(toCamelCase(field_schema.shortname), field_class(**field_kwargs))


def _build_serializer_related_id_field(
    serializer_part: SerializerAssemblyLine, model_field: models.Field
):
    """Build the ``FIELD_id`` field for a related field."""
    camel_id_name = toCamelCase(model_field.attname)
    serializer_part.add_field_name(camel_id_name, source=model_field.attname)

    # TODO: Temp. For backwards compatibility with accidentally exposing shortnames:
    field_schema = DynamicModel.get_field_schema(model_field)
    if _needs_shortname_compatibility(field_schema, model_field):
        logger.debug("Adding shortname compat for related ID %s", field_schema)
        serializer_part.add_field_name(
            toCamelCase(field_schema.shortname) + "Id", source=model_field.attname
        )


def _build_serializer_reverse_fk_field(
    serializer_part: SerializerAssemblyLine,
    model_field: models.ManyToOneRel,
):
    """Build the ManyToOneRel field"""
    field_schema = DynamicModel.get_field_schema(model_field)
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
        serializer_part.add_field(name, fields.RelatedSummaryField())
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
    return field_cls(
        view_name=get_view_name(target_model, "detail"),
        read_only=True,  # avoids having to add a queryset
        source="*",  # reads whole object, but only takes 'lookup_field' for the ID.
        lookup_field=lookup_field,
        **kwargs,
    )


def _generate_nested_relations(
    serializer_part: SerializerAssemblyLine, model: type[DynamicModel], nesting_level: int
):
    """Include fields that are implemented using nested tables."""
    table_schema = model.table_schema()
    schema_fields = {f.python_name: f for f in table_schema.fields}
    for model_field in model._meta.related_objects:
        # Do not create fields for django-created relations.
        field: DatasetFieldSchema | None = schema_fields.get(model_field.name)
        if field is not None and field.is_nested_table:
            related_serializer = serializer_factory(
                model_field.related_model,
                nesting_level=nesting_level + 1,
            )
            field_kwargs = {"source": model_field.name} if model_field.name != field.name else {}
            serializer_part.add_field(field.name, related_serializer(many=True, **field_kwargs))
