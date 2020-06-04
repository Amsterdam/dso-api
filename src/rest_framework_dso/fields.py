from typing import Type

from django.db import models
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

    def get_related_id(self, instance):
        """Return the "ID" value that is referenced to."""
        raise NotImplementedError()

    def get_related_ids(self, instances) -> list:
        """Return the "ID" values that is referenced to."""
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


class EmbeddedField(AbstractEmbeddedField):
    """An embedded field for a foreign-key relation."""

    def get_related_id(self, instance):
        """Find the _id field value"""
        return getattr(instance, self.attname)

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


class VersionedGetUrlMixin:
    def get_url(self, obj, view_name, request, format=None):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        # note that `obj` has only PK field.
        lookup_value, version = obj.pk.split("_")
        kwargs = {self.lookup_field: lookup_value}

        base_url = self.reverse(
            view_name, kwargs=kwargs, request=request, format=format
        )
        if hasattr(request.dataset, "versioning"):
            if request.dataset_version is not None:
                base_url = "{}?{}={}".format(
                    base_url,
                    request.dataset.versioning["version_field_name"],
                    request.dataset_version,
                )
            elif request.dataset_temporal_slice is not None:
                key = request.dataset_temporal_slice["key"]
                value = request.dataset_temporal_slice["value"]
                base_url = "{}?{}={}".format(base_url, key, value)
        else:
            base_url = self.reverse(
                view_name, kwargs=kwargs, request=request, format=format
            )
        return base_url


class VersionedHyperlinkedRelatedField(
    VersionedGetUrlMixin, serializers.HyperlinkedRelatedField
):
    pass


class VersionedReadOnlyField(serializers.ReadOnlyField):
    def to_representation(self, value):
        # Unsaved objects will not yet have a valid URL.
        if "request" in self.parent.context and hasattr(
            self.parent.context["request"].dataset, "versioning"
        ):
            value = value.split("_")[0]
        return value


class LinksField(serializers.HyperlinkedIdentityField):
    """Internal field to generate the _links bit"""

    def get_url(self, obj, view_name, request, format):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        kwargs = {self.lookup_field: obj.pk}

        if not hasattr(request.dataset, "versioning"):
            return super().get_url(obj, view_name, request, format)

        lookup_value = getattr(obj, request.dataset.versioning["pk_field_name"])
        kwargs = {self.lookup_field: lookup_value}
        base_url = self.reverse(
            view_name, kwargs=kwargs, request=request, format=format
        )

        version = getattr(obj, request.dataset.versioning["version_field_name"])
        return "{}?{}={}".format(
            base_url, request.dataset.versioning["request_parameter"], version
        )

    def to_representation(self, value):
        request = self.context.get("request")
        return {
            "self": {
                "href": self.get_url(value, self.view_name, request, None),
                "title": str(value),
            },
        }
