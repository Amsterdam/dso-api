import inspect
from collections import OrderedDict
from typing import Dict, List, Optional, Union, cast

from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.fields import URLField, empty
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_gis.fields import GeometryField

from rest_framework_dso.crs import CRS
from rest_framework_dso.embedding import EmbeddedResultSet, ObservableIterator, get_expanded_fields
from rest_framework_dso.fields import DSOGeometryField, EmbeddedField, LinksField
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable


class _SideloadMixin:
    """Handling ?_expand / ?_expandScope parameter.

    This is only a separate mixin because the parameter needs to be handled
    in 2 separate classes: `DSOListSerializer` and the regular `DSOSerializer`.
    """

    expand_all_param = "_expand"
    expand_param = "_expandScope"  # so ?_expandScope=.. gives a result
    expand_field = "_embedded"  # with _embedded in the result

    def __init__(self, *args, fields_to_expand=empty, **kwargs):
        super().__init__(*args, **kwargs)
        self._fields_to_expand = fields_to_expand

    @property
    def fields_to_expand(self) -> Union[list, bool]:
        """Retrieve the requested expand, 2 possible values:

        * A bool (True) for "expand all"
        * A explicit list of field names to expand.
        """
        if self._fields_to_expand is not empty:
            # Instead of retrieving this from request,
            # the expand can be defined using the serializer __init__.
            return cast(list, self._fields_to_expand)

        request = self.context["request"]

        # Initialize from request
        expand = request.GET.get(self.expand_all_param)
        if expand == "true":
            # ?_expand=true should export all fields
            return True
        elif expand:
            raise ParseError(
                "Only _expand=true is allowed. Use _expandScope to expanding specific fields."
            ) from None

        # otherwise, parse as a list of fields to expand.
        expand = request.GET.get(self.expand_param)
        return expand.split(",") if expand else False

    def get_expanded_fields(self) -> Dict[str, EmbeddedField]:
        """Retrieve the embedded fields for this request."""
        raise NotImplementedError("child serializer should implement this")


class DSOListSerializer(_SideloadMixin, serializers.ListSerializer):
    """Fix pagination for lists.

    This should be used together with the DSO...Pagination class when results are paginated.
    It outputs the ``_embedded`` section for the HAL-JSON spec:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    #: The field name for the results envelope
    results_field = None
    # DSO serializers require request in order to limit fields in representation.
    requires_context = True

    def __init__(self, *args, results_field=None, **kwargs):
        super().__init__(*args, **kwargs)
        if results_field:
            self.results_field = results_field
        elif not self.results_field:
            self.results_field = self.child.Meta.model._meta.model_name

    def get_expanded_fields(self) -> Dict[str, EmbeddedField]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        fields = self.fields_to_expand
        if not fields:
            return {}

        if not request.accepted_renderer.supports_list_embeds:
            raise ParseError("Embedding objects is not supported for this output format")
        return get_expanded_fields(self.child, fields)

    @property
    def data(self):
        ret = super(serializers.ListSerializer, self).data
        if isinstance(ret, dict):
            # Override to make sure dict is preserved
            return ReturnDict(ret, serializer=self)
        elif inspect.isgenerator(ret):
            # Override to make sure the generator is preserved
            return ReturnGenerator(ret, serializer=self)
        else:
            # Normal behavior
            return ReturnList(ret, serializer=self)

    def to_representation(self, data):
        """Improved list serialization.

        * It includes the data for the HAL "_embedded" section.
        * It reads the database with a streaming iterator to reduce memory.
        * It collects any embedded sections, and queries them afterwards
        """
        if self.root is not self or not isinstance(data, models.QuerySet):
            # When generating as part of an sub-object, just output the list.
            return super().to_representation(data)

        # Add any HAL-style sideloading if these were requested
        queryset_iterator = data.iterator()
        embedded_fields = {}

        if expanded_fields := self.get_expanded_fields():
            # All embedded result sets are updated during the iteration over
            # the main data with the relevant ID's to fetch on-demand.
            embedded_fields = {
                name: EmbeddedResultSet(field, serializer=field.get_serializer(self.child))
                for name, field in expanded_fields.items()
            }

            # Wrap the main object inside an observer, which notifies all
            # embedded sets about the retrieved objects. They prepare their
            # data retrieval accordingly.
            queryset_iterator = ObservableIterator(
                queryset_iterator,
                observers=[result_set.inspect_instance for result_set in embedded_fields.values()],
            )

        # Only when we're the root structure, consider returning a dictionary.
        # DSO always mandates a dict structure: {"objectname": [...]}
        #
        # The generator syntax tricks DRF into reading the source bit by bit,
        # without caching the whole queryset into memory.
        items = (self.child.to_representation(item) for item in queryset_iterator)

        # Make sure the first to_representation() is called early on. This makes sure
        # DSOModelSerializer.to_representation() can inspect the CRS, and define the
        # HTTP header for the Content-Crs setting. This will be too late when the streaming
        # rendering started. As bonus, it's a good guard against database errors, since those
        # exceptions might not be nicely rendered either once streaming started.
        _, items = peek_iterable(items)

        if not self.context["request"].accepted_renderer.supports_list_embeds:
            return items
        else:
            return {self.results_field: items, **embedded_fields}


class DSOSerializer(_SideloadMixin, serializers.Serializer):
    """Basic non-model serializer logic.

    This class implements all logic that can be used by all serializers,
    including those which are not based on database models.
    """

    # Requires context in order to limit fields in representation.
    requires_context = True

    fields_param = "_fields"  # so ?_fields=.. gives a result
    _default_list_serializer_class = DSOListSerializer

    @classmethod
    def many_init(cls, *args, **kwargs):
        """The initialization for many=True.

        This overrides the default ``list_serializer_class`` so it
        also returns HAL-style pagination and possibly embedding.
        """
        # Taken from base method
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {
            "child": child_serializer,
            "fields_to_expand": kwargs.pop("fields_to_expand", empty),
        }
        list_kwargs.update(
            {
                key: value
                for key, value in kwargs.items()
                if key in serializers.LIST_SERIALIZER_KWARGS
            }
        )

        # Reason for overriding this method: have a different default list_serializer_class
        meta = getattr(cls, "Meta", None)
        list_serializer_class = getattr(
            meta, "list_serializer_class", cls._default_list_serializer_class
        )

        # results field uses model_name if possible.
        list_kwargs["results_field"] = getattr(meta, "many_results_field", None)

        return list_serializer_class(*args, **list_kwargs)

    def get_fields(self):
        # .get() is needed to print serializer fields during debugging
        request = self.context.get("request")
        fields = super().get_fields()

        if request is None:
            # request would be be None for get_schema_view(public=True),
            # any other situation could be the basis for an information leak, hence abort here.
            raise RuntimeError(
                "Request object should be provided to serializer to apply security-restrictions"
            )

        # Adjust the serializer based on the request.
        request_fields = request.GET.get(self.fields_param)
        if not request_fields and "fields" in request.GET:
            request_fields = request.GET["fields"]  # DSO 1.0

        if request_fields:
            display_fields = self.get_fields_to_display(fields, request_fields)

            # Limit result to requested fields only
            fields = OrderedDict(
                [
                    (field_name, field)
                    for field_name, field in fields.items()
                    if field_name in display_fields
                ]
            )
        return fields

    def get_fields_to_display(self, fields, request_fields) -> set:
        """Tell which fields should be displayed"""
        display_fields = set(request_fields.split(","))

        invalid_fields = display_fields - set(fields.keys())
        if invalid_fields:
            # Some of `display_fields` are not in result.
            raise ValidationError(
                "'{}' is not one of available options".format("', '".join(sorted(invalid_fields))),
                code="fields",
            )
        return display_fields

    def get_expanded_fields(self) -> Dict[str, EmbeddedField]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        fields = self.fields_to_expand
        if not fields:
            return {}

        if not request.accepted_renderer.supports_detail_embeds:
            raise ParseError("Embedding objects is not supported for this output format")
        return get_expanded_fields(self, fields)

    @cached_property
    def _geometry_fields(self) -> List[GeometryField]:
        # Allow classes to exclude fields (e.g. a "point_wgs84" field shouldn't be used.)
        try:
            exclude_crs_fields = self.Meta.exclude_crs_fields
        except AttributeError:
            # e.g. non-model serializer, or no "exclude_crs_fields" defined.
            exclude_crs_fields = ()

        return [
            field
            for name, field in self.fields.items()
            if isinstance(field, GeometryField) and field.field_name not in exclude_crs_fields
        ]

    @cached_property
    def _url_content_fields(self) -> List[URLField]:
        """ indicates if model contains a URLField type so the content can be URL encoded """
        return [
            field_name
            for field_name, field_class in self.fields.items()
            if isinstance(field_class, URLField)
        ]

    def to_representation(self, instance):
        """Check whether the geofields need to be transformed."""
        if self._geometry_fields:
            request = self.context["request"]
            accept_crs: CRS = request.accept_crs  # Mandatory for DSO!
            if accept_crs is not None:
                self._apply_crs(instance, accept_crs)
                request.response_content_crs = accept_crs
            else:
                # Write back the used content CRS to include in the response.
                if request.response_content_crs is None:
                    request.response_content_crs = self._get_crs(instance)

        return super().to_representation(instance)

    def _apply_crs(self, instance, accept_crs: CRS):
        """Make sure all geofields use the same CRS."""
        for field in self._geometry_fields:
            geo_value = getattr(instance, field.source)
            if geo_value is not None:
                accept_crs.apply_to(geo_value)

    def _get_crs(self, instance) -> Optional[CRS]:
        """Find the used CRS in the geometry field(s)."""
        for field in self._geometry_fields:
            if isinstance(instance, dict):
                # non-model Serializer
                geo_value = instance[field.source]
            else:
                # ModelSerializer
                geo_value = getattr(instance, field.source)

            if geo_value is not None:
                # NOTE: if the same object uses multiple geometries
                # with a different SRID's, this ignores such case.
                return CRS.from_srid(geo_value.srid)

        return None


class DSOModelListSerializer(DSOListSerializer):
    """Perform object embedding for lists.

    This should be used together with the DSO...Pagination class when results are paginated.
    It outputs the ``_embedded`` section for the HAL-JSON spec:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    # Fetcher function to be overridden by subclasses if needed
    id_based_fetcher = None


class DSOModelSerializer(DSOSerializer, serializers.HyperlinkedModelSerializer):
    """DSO-compliant serializer.

    This supports the following extra's:
    - self-url is generated in a ``_links`` section.
    - Embedded relations are returned in an ``_embedded`` section.
    - Geometry values are converted into a single coordinate reference system
      (using ``request.accept_crs``)
    - ``request.response_content_crs`` is filled with the used CRS value.

    To use the embedding feature, include an ``EmbeddedField`` field in the class::

        class SomeSerializer(HALEmbeddedSerializer):
            embedded_field = EmbeddedField(SerializerClass)

            class Meta:
                model = ...
                fields = [...]

    The embedded support works on the ``ForeignKey`` field so far.
    """

    _default_list_serializer_class = DSOModelListSerializer
    serializer_field_mapping = {
        **serializers.HyperlinkedModelSerializer.serializer_field_mapping,
        # Override what django_rest_framework_gis installs in the app ready() signal:
        gis_models.GeometryField: DSOGeometryField,
        gis_models.PointField: DSOGeometryField,
        gis_models.LineStringField: DSOGeometryField,
        gis_models.PolygonField: DSOGeometryField,
        gis_models.MultiPointField: DSOGeometryField,
        gis_models.MultiLineStringField: DSOGeometryField,
        gis_models.MultiPolygonField: DSOGeometryField,
        gis_models.GeometryCollectionField: DSOGeometryField,
    }

    url_field_name = "self"
    serializer_url_field = LinksField

    # Fetcher function to be overridden by subclasses if needed
    id_based_fetcher = None

    def _include_embedded(self):
        """Determines if the _embedded field must be generated."""
        return self.root is self

    def to_representation(self, instance):
        """Check whether the geofields need to be transformed."""
        ret = super().to_representation(instance)

        # See if any HAL-style sideloading was requested
        if self._include_embedded():
            if expanded_fields := self.get_expanded_fields():
                ret[self.expand_field] = self._get_expand(instance, expanded_fields)

        return ret

    def _get_expand(self, instance, expanded_fields):
        expanded = {}
        for name, field in expanded_fields.items():
            # This just reuses the machinery for listings
            result_set = EmbeddedResultSet(
                field, serializer=field.get_serializer(self), main_instances=[instance]
            )

            if not field.is_array:
                # Single object, embed as dict directly
                expanded[name] = next(iter(result_set), None)
            else:
                # M2M relation, include as list (no need to delay this).
                expanded[name] = list(result_set)

        return expanded
