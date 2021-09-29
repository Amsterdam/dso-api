from __future__ import annotations

from typing import Optional, Union

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property
from more_itertools import first
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from schematools.contrib.django.models import LooseRelationField

from rest_framework_dso.utils import unlazy_object


def parse_request_fields(fields: Optional[str]):
    if not fields:
        return None

    # TODO: support nesting, perform validation
    return fields.split(",")


def get_embedded_field_class(
    model_field: Union[RelatedField, LooseRelationField, ForeignObjectRel]
) -> type[AbstractEmbeddedField]:
    """Return the embedded field type that is suited for a particular model field."""
    if isinstance(model_field, ForeignObjectRel):
        # Reverse relations
        if model_field.many_to_many:
            return EmbeddedManyToManyRelField
        else:
            return EmbeddedManyToOneRelField
    else:
        if model_field.one_to_many or model_field.many_to_many:
            return EmbeddedManyToManyField
        else:
            return EmbeddedField


class AbstractEmbeddedField:
    """A 'virtual' field that contains the configuration of an embedded field.

    Note this virtual field is *not* part of the serializer.fields,
    thus it's also **not** copied per instance. It's not possible to store
    request-state (such as the parent serializer object) in this class.

    There are two ways to include an embedded field in the serializer.
    Either add it as a class attribute (it will auto-register
    in ``Meta.embedded_fields``), or add it directly in ``Meta.embedded_fields``.
    Both styles require the serializer class to inherit
    from :class:`rest_framework_dso.serializers.ExpandMixin`.

    The embedded fields are designed to be efficient during streaming rendering
    of large datasets. Instead of collecting/prefetching the whole queryset in one go,
    the required relationship data is incrementally collected as each individual rendered
    object is written to the client. After rendering the whole first list of objects,
    the related objects can now be queried in a single SQL statement and be written
    to the next section in the ``"_embedded": { ... }`` dict.

    Hence, there are 2 significant overrides to implement:
    the :meth:`get_related_ids` method and :attr:`related_id_field` attribute.
    These define how a relationship is queried and should allow spanning FK/M2M
    and reverse ORM relations by playing with those 2 overrides.
    """

    def __init__(
        self,
        serializer_class: type[serializers.Serializer],
        *,
        source=None,
    ):
        self.serializer_class = serializer_class
        self.source = source

        self.field_name = None
        self.parent_serializer_class = None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.field_name}, {self.serializer_class.__name__}>"

    def __set_name__(self, owner, name):
        self.bind(owner, name)

    def bind(self, parent_serializer_class: type[serializers.Serializer], field_name: str):
        from .serializers import ExpandMixin

        if not issubclass(parent_serializer_class, ExpandMixin):
            raise TypeError(
                f"{parent_serializer_class} does not extend from DSO serializer classes"
            ) from None

        self.parent_serializer_class = parent_serializer_class
        self.field_name = field_name
        if self.source is None:
            self.source = self.field_name

        # Also register this field in the Meta.embedded,
        # which makes it easier to collect embedded relations
        meta = self.parent_serializer_class.Meta
        if not hasattr(meta, "embedded_fields"):
            meta.embedded_fields = {}
        meta.embedded_fields[field_name] = self

    def get_related_ids(self, instance):
        """Return the "ID" values that are referenced from a single instance
        This can be a FK or an NM relationship.
        """
        raise NotImplementedError()

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        """Build the EmbeddedField serializer object that can generate an embedded result.

        Since this virtual-field object persists between all sessions,
        the parent/root serializer needs to be provided here.
        Settings like ``fields_to_extend`` are provided via the **kwargs.
        """
        if not isinstance(parent, self.parent_serializer_class):
            raise TypeError(f"Invalid parent for {self.__class__.__name__}.get_serializer()")

        # Make sure the serializer is the true object, or other isinstance() checks will fail.
        self.serializer_class = unlazy_object(self.serializer_class)
        embedded_serializer = self.serializer_class(context=parent.context, **kwargs)
        embedded_serializer.bind(field_name=self.field_name, parent=parent)
        return embedded_serializer

    @cached_property
    def related_model(self) -> type[models.Model]:
        """Return the Django model class"""
        # Make sure the serializer is the true object, or other isinstance() checks will fail.
        self.serializer_class = unlazy_object(self.serializer_class)
        return self.serializer_class.Meta.model

    @property
    def related_id_field(self) -> Optional[str]:
        """The ID field is typically auto-detected.

        It can however be overwritten to change the object retrieval query.
        This is used by reverse relationships to retrieve objects
        from a related foreign key instead.
        """
        return None

    @cached_property
    def parent_model(self) -> type[models.Model]:
        """Return the Django model class"""
        return self.parent_serializer_class.Meta.model

    @cached_property
    def source_field(self) -> Union[models.Field, models.ForeignObjectRel]:
        return self.parent_model._meta.get_field(self.source)

    @cached_property
    def is_loose(self) -> bool:
        """ Signals that the related field is not a real FK or M2M """
        return not isinstance(self.source_field, (RelatedField, ForeignObjectRel))

    @cached_property
    def is_array(self) -> bool:
        """Whether the relation returns an list of items (e.g. ManyToMany)."""
        # This includes ManyToManyField, LooseRelationManyToManyField and ForeignObjectRel
        return self.source_field.many_to_many or self.source_field.one_to_many

    @cached_property
    def is_reverse(self) -> bool:
        """Whether the relation is actually a reverse relationship."""
        return isinstance(self.source_field, ForeignObjectRel)


class EmbeddedField(AbstractEmbeddedField):
    """An embedded field for a foreign-key relation.

    This collects the identifiers to the related foreign objects,
    so these can be queried once all main objects have been written to the client.
    """

    @cached_property
    def attname(self) -> str:
        try:
            # For ForeignKey/OneToOneField this resolves to "{field_name}_id"
            return self.source_field.attname
        except FieldDoesNotExist:
            # Allow non-FK relations, e.g. a "bag_id" to a completely different database
            if not self.source.endswith("_id"):
                return f"{self.source}_id"
            else:
                return self.source

    def get_related_ids(self, instance):
        """Find the _id field value(s)"""
        # The identifier of the foreign objects is known in the parent object. Becomes the query:
        # self.related_model.objects.filter({pk}__in=[ids to foreign instances])
        id_value = getattr(instance, self.attname, None)
        return [] if id_value is None else [id_value]


class EmbeddedManyToOneRelField(EmbeddedField):
    """An embedded field for reverse relations (of foreign keys).

    This collects the identifiers of all primary objects, so any objects
    that link to those primary objects can be resolved afterwards in a single query.

    The name of this object is somewhat awkward, but it follows Django conventions.
    Django ForeignKey's have a OneToManyRel that describes the relationship.
    That object is also placed on the foreign object as reverse field, thus giving the
    funny ``ManyToOneRel.one_to_many == True`` situation. The reverse field should have
    been called something like "OneToManyField" but Django reuses the "ManyToOneRel" there.
    """

    def get_related_ids(self, instance):
        """Reverse relations link to the given instance, hence we track the 'pk'."""
        return [instance.pk]

    @property
    def attname(self) -> str:
        """Reverse relations are based on the current object's identifier."""
        if self.parent_model.is_temporal():
            return first(self.parent_model.table_schema().identifier)
        else:
            return "pk"

    @property
    def related_id_field(self):
        """Change the ID field to implement reverse relations.
        This lets the results be read from the remote foreign key to retrieve the objects.
        """
        # This causes the queryset to be constructed as:
        # self.related_model.objects.filter({fk_field}__in=[ids to primary instances])
        return self.source_field.remote_field.name


class EmbeddedManyToManyField(AbstractEmbeddedField):
    """An embedded field for a M2M relation.

    This collects all identifiers of the primary objects, so the through table
    can be queried afterwards in a single call to find all related objects.
    """

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        kwargs.setdefault("many", True)
        return super().get_serializer(parent, **kwargs)

    def get_related_ids(self, instance):
        """The PK of this source object can be used to find the relation in the through table."""
        return [instance.pk]

    @cached_property
    def related_id_field(self) -> Optional[str]:
        # This causes the queryset to be constructed as:
        # self.related_model.objects.filter({reverse_through_field}__{idfield}__in=[PKs])
        return "__".join(
            path_info.join_field.name for path_info in self.source_field.get_reverse_path_info()
        )


class EmbeddedManyToManyRelField(EmbeddedManyToManyField):
    """Embedded field for reverse M2M relations.

    This performs roughly the same query as the forward M2M relation,
    except that the relation to the through table is followed backwards.
    """

    def related_id_field(self) -> Optional[str]:
        # This causes the queryset to be constructed as:
        # self.related_model.objects.filter({forward_through_field}__{identifierfield}__in=[PKs])
        return "__".join(
            path_info.join_field.name for path_info in self.source_field.get_path_info()
        )


class LinksField(serializers.HyperlinkedIdentityField):
    """Internal field to generate the _links bit"""

    def to_representation(self, value):
        request = self.context.get("request")

        output = {"href": self.get_url(value, self.view_name, request, None)}

        # if no display field, ommit the title element from output
        if value._display_field:
            output.update({"title": str(value)})

        if value.is_temporal():
            temporal_fieldname = value.table_schema().temporal.identifier
            temporal_value = getattr(value, temporal_fieldname)
            id_fieldname = first(value.table_schema().identifier)

            id_value = getattr(value, id_fieldname)
            output.update({temporal_fieldname: temporal_value, id_fieldname: id_value})

        return output


class DSOGeometryField(GeometryField):
    """Extended geometry field to properly handle export formats."""

    @cached_property
    def _output_format(self):
        # caching this object retrieval helps performance in CSV exports.
        # no need to resolve the root serializer all the time.
        request = self.context.get("request")
        if request is None:
            return None

        return request.accepted_renderer.format

    def to_representation(self, value):
        """Avoid GeoJSON export format for e.g. CSV exports"""
        if value is None:
            return None
        elif self._output_format == "csv":
            # Extended well-known text for CSV format.
            return value.ewkt
        else:
            # Return GeoJSON for json/html/api formats
            return super().to_representation(value)


class HALHyperlinkedRelatedField(serializers.HyperlinkedRelatedField):
    """Wrap the url from the HyperlinkedRelatedField according to HAL specs"""

    def to_representation(self, value):
        href = super().to_representation(value)
        return {"href": href, "title": str(value.pk)}


class GeoJSONIdentifierField(serializers.Field):
    """A field that renders the "id" field for a GeoJSON feature."""

    def __init__(self, model=None, **kwargs):
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        super().__init__(**kwargs)
        self.model = model

    def bind(self, field_name, parent):
        super().bind(field_name, parent)
        if self.model is None:
            self.model = parent.Meta.model

    def to_representation(self, value):
        return f"{self.model._meta.object_name}.{value.pk}"
