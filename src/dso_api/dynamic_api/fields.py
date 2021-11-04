from datetime import datetime, timedelta

import azure.storage.blob
from django.conf import settings
from more_ds.network.url import URL
from more_itertools import first
from rest_framework import serializers
from rest_framework.reverse import reverse
from schematools.types import DatasetTableSchema
from schematools.utils import to_snake_case

from .temporal import TemporalTableQuery
from .utils import split_on_separator


class TemporalHyperlinkedRelatedField(serializers.HyperlinkedRelatedField):
    """Temporal Hyperlinked Related Field

    Used for forward relations in serializers."""

    def __init__(self, table_schema: DatasetTableSchema, *args, **kwargs):
        # Init adds temporal definitions at construction, removing runtime model lookups.
        # It also allows the PK optimization to be used.
        super().__init__(*args, **kwargs)
        self.table_schema = table_schema

    def use_pk_only_optimization(self):
        return True  # only need to have an "id" here.

    def get_url(self, obj, view_name, request, format=None):
        """Generate /path/{identificatie}/?volgnummer=... links."""
        if hasattr(obj, "pk") and obj.pk in (None, ""):
            # Unsaved objects will not yet have a valid URL.
            return None

        # NOTE: this one splits on the Django "id" field instead of
        # reading the "identificatie" / "volgnummer" fields directly.
        # It does allow use_pk_only_optimization() when lookup_field == "pk".
        id_value, id_version = split_on_separator(getattr(obj, self.lookup_field))
        base_url = self.reverse(
            view_name, kwargs={self.lookup_url_kwarg: id_value}, request=request, format=format
        )

        temporal = TemporalTableQuery(request, self.table_schema)
        url_args = (
            temporal.url_parameters  # e.g. {"geldigOp": ...}
            if temporal.slice_dimension
            else {self.table_schema.temporal.identifier: id_version}
        )
        return URL(base_url) // url_args


class TemporalReadOnlyField(serializers.ReadOnlyField):
    """Temporal Read Only Field

    Used for Primary Keys in serializers.
    """

    def to_representation(self, value):
        """Remove the version number from the relation value,
        typically done for RELATION_identificatie, RELATION_volgnummer fields.
        """
        # Split unconditionally. This field type should only be used
        # when the target model is a temporal relationship.
        return split_on_separator(value)[0]


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
