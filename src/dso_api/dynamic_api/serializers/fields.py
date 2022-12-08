"""Additional field types for serializers.

These fields handle custom output for some specific nodes in the "tree of fields".
Standard field types are handled by the standard REST Framework fields.

Note that the fields mainly output a plain scalar value. When a dictionary is returned
by ``to_representation()``, the field also needs to define the OpenAPI details on
what the field would return. Hence, other fields (e.g. in ``_links``) that return
more variable fields are constructed as a serializer instead.
"""
from urllib.parse import urlencode

from django.db import models
from drf_spectacular.utils import extend_schema_field, inline_serializer
from more_ds.network.url import URL
from rest_framework import serializers
from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.reverse import reverse
from rest_framework.serializers import Field
from schematools.naming import toCamelCase
from schematools.types import DatasetTableSchema

from dso_api.dynamic_api.temporal import TemporalTableQuery
from dso_api.dynamic_api.utils import get_view_name, split_on_separator


@extend_schema_field(
    # Tell what this field will generate as object structure
    inline_serializer(
        "RelatedSummary",
        fields={
            "count": serializers.IntegerField(),
            "href": serializers.URLField(),
        },
    )
)
class RelatedSummaryField(Field):
    def to_representation(self, value: models.Manager):
        request = self.context["request"]
        url = reverse(get_view_name(value.model, "list"), request=request)

        # the "core_filters" attribute is available on all related managers
        filter_field = next(iter(value.core_filters.keys()))
        q_params = {toCamelCase(filter_field + "_id"): value.instance.pk}

        # If this is a temporal table, only return the appropriate records.
        if value.model.is_temporal():
            # The essence of filter_temporal_slice()
            query = TemporalTableQuery.from_request(request, value.model.table_schema())
            q_params.update(query.url_parameters)
            value = query.filter_queryset(value.all())

        query_string = ("&" if "?" in url else "?") + urlencode(q_params)
        return {"count": value.count(), "href": f"{url}{query_string}"}


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
        try:
            id_value = getattr(obj, self.lookup_field)
            id_value, id_version = split_on_separator(id_value)
        except ValueError as e:
            if str(e).startswith("not enough values to unpack"):  # Missing "volgnummer".
                id_version = "*"
            else:
                raise

        base_url = self.reverse(
            view_name, kwargs={self.lookup_url_kwarg: id_value}, request=request, format=format
        )

        temporal = TemporalTableQuery.from_request(request, self.table_schema)
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
        # The str() cast makes the core more robust, in case the underlying
        # database returns an integer instead of the expected string.
        return split_on_separator(str(value))[0]


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
