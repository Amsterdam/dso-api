from rest_framework import serializers
from rest_framework_dso.fields import LinksField


class TemporalHyperlinkedRelatedField(serializers.HyperlinkedRelatedField):
    """Temporal Hyperlinked Related Field

    Usef for forward relations in serializers."""

    def get_url(self, obj, view_name, request, format=None):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        if request.versioned:
            # note that `obj` has only PK field.
            lookup_value, version = obj.pk.split("_")
            kwargs = {self.lookup_field: lookup_value}

            base_url = self.reverse(
                view_name, kwargs=kwargs, request=request, format=format
            )
            if request.dataset_temporal_slice is None:
                key = request.dataset.temporal.get("identifier")
                value = version
            else:
                key = request.dataset_temporal_slice["key"]
                value = request.dataset_temporal_slice["value"]
            base_url = "{}?{}={}".format(base_url, key, value)
        else:
            kwargs = {self.lookup_field: obj.pk}
            base_url = self.reverse(
                view_name, kwargs=kwargs, request=request, format=format
            )
        return base_url


class TemporalReadOnlyField(serializers.ReadOnlyField):
    """Temporal Read Only Field

    Used for Primary Keys in serializers.
    """

    def to_representation(self, value):
        if (
            "request" in self.parent.context
            and self.parent.context["request"].versioned
        ):
            value = value.split("_")[0]
        return value


class TemporalLinksField(LinksField):
    """Versioned Links Field

    Correcting URLs inside Links field with proper versions.
    """

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        kwargs = {self.lookup_field: obj.pk}

        if request.dataset.temporal is None:
            return super().get_url(obj, view_name, request, format)

        lookup_value = getattr(obj, request.dataset.identifier)
        kwargs = {self.lookup_field: lookup_value}
        base_url = self.reverse(
            view_name, kwargs=kwargs, request=request, format=format
        )

        temporal_identifier = request.dataset.temporal["identifier"]
        version = getattr(obj, temporal_identifier)
        return "{}?{}={}".format(base_url, temporal_identifier, version)
