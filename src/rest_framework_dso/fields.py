from typing import Type

from django.db import models
from django.utils.functional import cached_property
from rest_framework.serializers import Serializer


class AbstractEmbeddedField:
    """A 'virtual' field that contains the configuration of an embedded field."""

    def __init__(
        self, serializer_class: Type[Serializer], *, to_field=None, source=None
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

    def get_related_id(self, instance):
        """Return the "ID" value that is referenced to."""
        raise NotImplementedError()

    def get_related_ids(self, instances) -> list:
        """Return the "ID" values that is referenced to."""
        raise NotImplementedError()

    def get_serializer(self, parent: Serializer) -> Serializer:
        """Build the EmbeddedFieldserializer object that can generate an embedded result."""
        embedded_serializer = self.serializer_class(context=parent.context)
        embedded_serializer.bind(field_name=self.field_name, parent=parent)
        return embedded_serializer

    @cached_property
    def related_model(self) -> Type[models.Model]:
        """Return the Django model class"""
        return self.serializer_class.Meta.model


class EmbeddedField(AbstractEmbeddedField):
    """An embedded field for a foreign-key relation."""

    def get_related_id(self, instance):
        """Find the _id field value"""
        return getattr(instance, self.attname, None)

    def get_related_ids(self, instances) -> list:
        """Find the object IDs of the instances."""
        return list(
            filter(None, [getattr(instance, self.attname) for instance in instances])
        )

    @cached_property
    def attname(self):
        field_name = self.source or self.field_name
        try:
            # For ForeignKey/OneToOneField this resolves to "{field_name}_id"
            return self.related_model._meta.get_field(field_name).attname
        except models.FieldDoesNotExist:
            # Allow non-FK relations, e.g. a "bag_id" to a completely different database
            if not field_name.endswith("_id"):
                return f"{field_name}_id"
            else:
                return field_name
