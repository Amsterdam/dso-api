from typing import Type

from django.db import models
from django.db.models.fields.related import RelatedField
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField


class AbstractEmbeddedField:
    """A 'virtual' field that contains the configuration of an embedded field.

    Note this virtual field is *not* part of the serializer.fields,
    thus it's also **not** copied per instance. It's not possible to store
    request-state (such as the parent serializer object) in this class.
    """

    def __init__(
        self,
        serializer_class: Type[serializers.Serializer],
        *,
        source=None,
    ):
        self.serializer_class = serializer_class
        self.source = source

        self.field_name = None
        self.parent_serializer_class = None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.field_name}>"

    def __set_name__(self, owner, name):
        from .serializers import _SideloadMixin

        if not issubclass(owner, _SideloadMixin):
            raise TypeError(f"{owner} does not extend from DSO serializer classes") from None

        self.parent_serializer_class = owner
        self.field_name = name

        # Also register this field in the Meta.embedded,
        # which makes it easier to collect embedded relations
        meta = self.parent_serializer_class.Meta
        if not hasattr(meta, "embedded_fields"):
            meta.embedded_fields = []
        meta.embedded_fields.append(name)

    def get_related_ids(self, instance):
        """Return the "ID" values that are referenced from a single instance
        This can be a FK or an NM relationship.
        """
        raise NotImplementedError()

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        """Build the EmbeddedField serializer object that can generate an embedded result.

        Since this virtual-field object persists between all sessions,
        the parent/root serializer needs to be provided here.
        """
        if not isinstance(parent, self.parent_serializer_class):
            raise TypeError(f"Invalid parent for {self.__class__.__name__}.get_serializer()")

        embedded_serializer = self.serializer_class(context=parent.context, **kwargs)
        embedded_serializer.bind(field_name=self.field_name, parent=parent)
        return embedded_serializer

    @cached_property
    def related_model(self) -> Type[models.Model]:
        """Return the Django model class"""
        return self.serializer_class.Meta.model

    @cached_property
    def parent_model(self) -> Type[models.Model]:
        """Return the Django model class"""
        return self.parent_serializer_class.Meta.model

    @cached_property
    def source_field(self):
        field_name = self.source or self.field_name
        return self.parent_model._meta.get_field(field_name)

    @cached_property
    def is_loose(self) -> bool:
        """ Signals that the related field is not a real FK or M2M """
        return not isinstance(self.source_field, RelatedField)

    @cached_property
    def is_array(self) -> bool:
        """Whether the relation returns an list of items (e.g. ManyToMany)."""
        # This includes LooseRelationManyToManyField
        return isinstance(self.source_field, models.ManyToManyField)

    @cached_property
    def attname(self):
        field_name = self.source or self.field_name
        try:
            # For ForeignKey/OneToOneField this resolves to "{field_name}_id"
            # For ManyToManyField this resolves to a manager object
            return self.parent_model._meta.get_field(field_name).attname
        except models.FieldDoesNotExist:
            # Allow non-FK relations, e.g. a "bag_id" to a completely different database
            if not field_name.endswith("_id"):
                return f"{field_name}_id"
            else:
                return field_name


class EmbeddedField(AbstractEmbeddedField):
    """An embedded field for a foreign-key relation."""

    def get_related_ids(self, instance):
        """Find the _id field value(s)"""
        id_value = getattr(instance, self.attname, None)
        return [] if id_value is None else [id_value]


class EmbeddedManyToManyField(AbstractEmbeddedField):
    """An embedded field for a n-m relation."""

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        kwargs.setdefault("many", True)
        return super().get_serializer(parent, **kwargs)

    def get_related_ids(self, instance):
        """Find the _id field value(s)"""
        related_mgr = getattr(instance, self.attname, None)
        if related_mgr is None:
            return []
        # I guess, as long as it is Django we can use pk,
        # because Django needs it
        source_is_temporal = self.parent_model.is_temporal()
        target_is_temporal = related_mgr.model.is_temporal()
        if not source_is_temporal and target_is_temporal:
            ids = self._get_temporal_ids(instance, related_mgr)
        else:
            ids = [r.pk for r in related_mgr.all()]
        return ids

    def _get_temporal_ids(self, instance, related_mgr):
        (
            identificatie_fieldname,
            volgnummer_fieldname,
        ) = related_mgr.model._table_schema.identifier
        source_field_name = related_mgr.source_field_name
        source_id = instance.id
        through_tabel_filter_params = {source_field_name: source_id}
        target_id_field = f"{related_mgr.target_field_name}_id"
        through_tabel_items = related_mgr.through.objects.filter(
            **through_tabel_filter_params
        ).values_list(target_id_field, flat=True)
        target_filter_params = {f"{identificatie_fieldname}__in": through_tabel_items}
        order_param = f"-{volgnummer_fieldname}"
        ids = (
            related_mgr.model.objects.filter(**target_filter_params)
            .order_by(order_param)
            .values_list("pk", flat=True)[:1]
        )
        return ids


class LinksField(serializers.HyperlinkedIdentityField):
    """Internal field to generate the _links bit"""

    def to_representation(self, value):
        request = self.context.get("request")

        output = {"href": self.get_url(value, self.view_name, request, None)}

        # if no display field, ommit the title element from output
        if value._display_field:
            output.update({"title": str(value)})

        if value.is_temporal():
            temporal_fieldname = value.get_dataset().temporal.get("identifier")
            temporal_value = getattr(value, temporal_fieldname)
            id_fieldname = value.get_dataset().get("identifier")
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
