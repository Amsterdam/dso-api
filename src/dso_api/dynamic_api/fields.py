from datetime import datetime, timedelta
from typing import Any, cast

import azure.storage.blob
from django.conf import settings
from more_ds.network.url import URL
from more_itertools import first
from rest_framework import serializers
from rest_framework.reverse import reverse
from schematools.contrib.django.models import DynamicModel
from schematools.types import Temporal
from schematools.utils import to_snake_case

from rest_framework_dso.fields import LinksField

from .utils import split_on_separator


class TemporalHyperlinkedRelatedField(serializers.HyperlinkedRelatedField):
    """Temporal Hyperlinked Related Field

    Used for forward relations in serializers."""

    def use_pk_only_optimization(self):
        # disable, breaks obj.is_temporal()
        return False

    def get_url(self, obj, view_name, request, format=None):
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        if obj.is_temporal():
            # note that `obj` has only PK field.
            lookup_value, version = split_on_separator(obj.pk)
            kwargs = {self.lookup_field: lookup_value}

            base_url = self.reverse(view_name, kwargs=kwargs, request=request, format=format)
            if request.table_temporal_slice is None:
                key = obj.table_schema().temporal.identifier
                value = version
            else:
                key = request.table_temporal_slice["key"]
                value = request.table_temporal_slice["value"]

            base_url = URL(base_url) // {key: value}
        else:
            kwargs = {self.lookup_field: obj.pk}
            base_url = self.reverse(view_name, kwargs=kwargs, request=request, format=format)
        return base_url


class HALTemporalHyperlinkedRelatedField(TemporalHyperlinkedRelatedField):
    """Wrap the url from the HyperlinkedRelatedField according to HAL specs.

    If the value is from a temporal table, extra info is added to the output.
    """

    def to_representation(self, value: DynamicModel):
        href = super().to_representation(value)
        table_schema = value.table_schema()
        id_fieldname = first(table_schema.identifier)

        output: dict[str, Any] = {"href": href, id_fieldname: getattr(value, id_fieldname)}
        if value.has_display_field():
            output["title"] = str(value)

        if href and value.is_temporal():
            temporal: Temporal = cast(Temporal, table_schema.temporal)
            temporal_fieldname = temporal.identifier

            # Add the temporal fields that uniquely identify the related object
            # (e.g. "identificatie" and "volgnummer" for GOB data).
            output.update(
                {
                    temporal_fieldname: getattr(value, temporal_fieldname),
                }
            )

        return output


class TemporalReadOnlyField(serializers.ReadOnlyField):
    """Temporal Read Only Field

    Used for Primary Keys in serializers.
    """

    def to_representation(self, value):
        """Remove the version number from the relation value,
        typically done for RELATION_identificatie, RELATION_volgnummer fields.
        """
        if "request" in self.parent.context and self.parent.context["request"].versioned:
            value = split_on_separator(value)[0]
        return value


class TemporalLinksField(LinksField):
    """Versioned Links Field

    Correcting URLs inside Links field with proper versions.
    """

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            return None

        kwargs = {self.lookup_field: obj.pk}

        if not obj.is_temporal():
            return super().get_url(obj, view_name, request, format)

        table_schema = obj.table_schema()
        lookup_value = getattr(obj, first(table_schema.identifier))

        kwargs = {self.lookup_field: lookup_value}
        base_url = self.reverse(view_name, kwargs=kwargs, request=request, format=format)

        table_schema = obj.table_schema()
        temporal_identifier = table_schema.temporal.identifier
        version = getattr(obj, temporal_identifier)
        return URL(base_url) // {temporal_identifier: version}


class AzureBlobFileField(serializers.ReadOnlyField):
    """Azure storage field."""

    def __init__(self, account_name, *args, **kwargs):
        self.account_name = account_name
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        if not value:
            return value
        blob_client = azure.storage.blob.BlobClient.from_blob_url(value)
        sas_token = azure.storage.blob.generate_blob_sas(
            self.account_name,
            blob_client.container_name,
            blob_client.blob_name,
            snapshot=blob_client.snapshot,
            account_key=getattr(settings, f"AZURE_BLOB_{self.account_name.upper()}", None),
            permission=azure.storage.blob.BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1),
        )

        if sas_token is None:
            return value
        return f"{value}?{sas_token}"


class LooseRelationUrlField(serializers.CharField):
    """A url field for very loose relations to temporal datasets
    The relation has to be defined as: "<dataset>:<table>:<column>" in the schema
    The specific definition of the column signals that the relation is
    very loose and a url is constructed without any checking.
    """

    def to_representation(self, value):
        from .urls import app_name

        request = self.context["request"]
        view = self.context["view"]
        relation = view.model._meta.get_field(to_snake_case(self.field_name)).relation
        dataset_name, table_name = (to_snake_case(part) for part in relation.split(":"))
        # We force that the incoming value is interpreted as the
        # pk, although this is not always the 'real' pk, e.g. for temporal relations
        kwargs = {"pk": value}
        return reverse(
            f"{app_name}:{dataset_name}-{table_name}-detail",
            kwargs=kwargs,
            request=request,
        )


class HALLooseRelationUrlField(LooseRelationUrlField):
    """Wrap the URL from LooseRelationUrlField according to HAL specs."""

    def to_representation(self, value):
        href = super().to_representation(value)
        view = self.context["view"]
        field = view.model._meta.get_field(to_snake_case(self.field_name))
        relation = field.relation
        dataset_name, table_name = (to_snake_case(part) for part in relation.split(":"))
        result = {"href": href}

        if view.model.has_display_field():
            result["title"] = str(value)

        related_identifier = first(field.related_model.table_schema().identifier)
        result[related_identifier] = value
        return result


class LooseRelationUrlListField(serializers.ListField):
    child = LooseRelationUrlField
