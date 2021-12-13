from datetime import datetime, timedelta

import azure.storage.blob
from django.conf import settings
from more_ds.network.url import URL
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from schematools.types import DatasetTableSchema

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
        # reading the temporal fields directly (e.g.: "identificatie"/"volgnummer").
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


class HALLooseRelationUrlField(HyperlinkedRelatedField):
    """Wrap the URL from LooseRelationUrlField according to HAL specs."""

    def use_pk_only_optimization(self):
        return True

    def get_url(self, obj, view_name, request, format=None):
        """Generate /path/{<primary_id>}/"""
        return self.reverse(
            view_name, kwargs={self.lookup_url_kwarg: obj}, request=request, format=format
        )


class HALLooseM2MUrlField(HALLooseRelationUrlField):
    def get_url(self, obj, *args, **kwargs):
        """Generate /path/{<primary_id>}/

        In case of a loose M2M, the runtime value is an entry from the intermediate table.
        """
        return super().get_url(getattr(obj, self.lookup_field), *args, **kwargs)
