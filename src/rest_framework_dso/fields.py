from typing import Type

from django.db import models
from django.db.models.fields.related import RelatedField
from django.utils.functional import cached_property
from rest_framework import serializers


class AbstractEmbeddedField:
    """A 'virtual' field that contains the configuration of an embedded field."""

    def __init__(
        self,
        serializer_class: Type[serializers.Serializer],
        *,
        to_field=None,
        source=None,
    ):
        self.serializer_class = serializer_class
        self.to_field = to_field
        self.source = source

        self.field_name = None
        self.parent_serializer = None

    def __set_name__(self, owner, name):
        from .serializers import _SideloadMixin

        if not issubclass(owner, _SideloadMixin):
            raise TypeError(
                f"{owner} does not extend from DSO serializer classes"
            ) from None

        self.parent_serializer = owner
        self.field_name = name

        # Also register this field in the Meta.embedded,
        # which makes it easier to collect embedded relations
        meta = self.parent_serializer.Meta
        if not hasattr(meta, "embedded_fields"):
            meta.embedded_fields = []
        meta.embedded_fields.append(name)

    def get_related_detail_ids(self, instance):
        """Return the "ID" values that are referenced from a single instance
        This can be a FK or an NM relationship.
        """
        raise NotImplementedError()

    def get_related_list_ids(self, instances) -> list:
        """Return the "ID" values that are referenced from a list of instances."""
        raise NotImplementedError()

    def get_serializer(self, parent: serializers.Serializer) -> serializers.Serializer:
        """Build the EmbeddedFieldserializer object that can generate an embedded result."""
        embedded_serializer = self.serializer_class(context=parent.context)
        embedded_serializer.bind(field_name=self.field_name, parent=parent)
        return embedded_serializer

    @cached_property
    def related_model(self) -> Type[models.Model]:
        """Return the Django model class"""
        return self.serializer_class.Meta.model

    @cached_property
    def parent_model(self) -> Type[models.Model]:
        """Return the Django model class"""
        return self.parent_serializer.Meta.model

    @cached_property
    def is_loose(self) -> bool:
        """ Signals that the related field is not a real FK or M2M """
        return not isinstance(
            self.parent_model._meta.get_field(self.source or self.field_name),
            RelatedField,
        )

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

    def get_related_detail_ids(self, instance):
        """Find the _id field value(s)"""
        id_value = getattr(instance, self.attname, None)
        return [] if id_value is None else [id_value]

    def get_related_list_ids(self, instances) -> list:
        """Find the object IDs of the instances."""
        return list(
            filter(None, [getattr(instance, self.attname) for instance in instances])
        )


class EmbeddedManyToManyField(AbstractEmbeddedField):
    """An embedded field for a n-m relation."""

    def get_related_detail_ids(self, instance):
        """Find the _id field value(s)"""
        related_mgr = getattr(instance, self.attname, None)
        if related_mgr is None:
            return []
        # I guess, as long as it is Django we can use pk,
        # because Django needs it
        return [r.pk for r in related_mgr.all()]

    def get_related_list_ids(self, instances) -> list:
        """Find the object IDs of the instances."""
        ids = set()
        for instance in instances:
            related_mgr = getattr(instance, self.attname, None)
            if related_mgr is None:
                continue
            ids |= set(r.pk for r in related_mgr.all())
        return list(ids)


class LinksField(serializers.HyperlinkedIdentityField):
    """Internal field to generate the _links bit"""

    def to_representation(self, value):
        request = self.context.get("request")

        output = {"self": {"href": self.get_url(value, self.view_name, request, None)}}

        # if no display field, ommit the title element from output
        if value._display_field:
            output["self"].update({"title": str(value)})

        return output
