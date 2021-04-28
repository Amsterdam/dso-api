"""The serializers implement additional DSO responses features.

Most features can be implemented by the following means:

1. Having the proper set of "fields" loaded in the serializer.
   These field classes determine the format of individual data types.
2. Overriding ``to_representation()`` where needed.

There are 2 layers of serializers, just like standard DRF:

* :class:`DSOSerializer` and it's cousin :class:`DSOListSerializer` that's used for ``many=True``.
* :class:`DSOModelSerializer` and :class:`DSOModelListSerializer`.

The non-model serializers implement the bits that are not dependant on database ORM logic
like models or querysets. These serializers are therefore more limited in functionality,
but useful to implement DSO-style responses for other data sources (e.g. remote API responses).

The model-serializers depend on the ORM logic, and support features like object embedding
and constructing serializer fields based on the model field metadata.
"""
import inspect
from collections import OrderedDict
from typing import List, Optional, Union, cast

from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.fields import URLField, empty
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_gis.fields import GeometryField

from rest_framework_dso.crs import CRS
from rest_framework_dso.embedding import (
    ChunkedQuerySetIterator,
    EmbeddedFieldMatch,
    EmbeddedResultSet,
    ObservableIterator,
    get_expanded_fields_by_scope,
    parse_expand_scope,
)
from rest_framework_dso.fields import DSOGeometryField, LinksField
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable


class _SideloadMixin:
    """Handling ?_expand / ?_expandScope parameter.

    This is only a separate mixin because the parameter needs to be handled
    in 2 separate classes: :class:`DSOListSerializer` and the regular :class:`DSOSerializer`.
    """

    expand_all_param = "_expand"
    expand_param = "_expandScope"  # so ?_expandScope=.. gives a result
    expand_field = "_embedded"  # with _embedded in the result

    def __init__(self, *args, fields_to_expand=empty, **kwargs):
        super().__init__(*args, **kwargs)
        self._fields_to_expand = fields_to_expand

    def has_fields_to_expand_override(self) -> bool:
        """Tell whether the 'fields_to_expand' is set by the code instead of request."""
        return self._fields_to_expand is not empty

    @property
    def fields_to_expand(self) -> Union[List[str], bool]:
        """Retrieve the requested expand, 2 possible values:

        * A bool (True) for "expand all"
        * A explicit list of field names to expand.
        """
        if self.has_fields_to_expand_override():
            # Instead of retrieving this from request,
            # the expand can be defined using the serializer __init__.
            return False if self._fields_to_expand is False else cast(list, self._fields_to_expand)
        else:
            # Parse from request
            request = self.context["request"]
            return parse_expand_scope(
                expand=request.GET.get(self.expand_all_param),
                expand_scope=request.GET.get(self.expand_param),
            )

    @fields_to_expand.setter
    def fields_to_expand(self, fields: List[str]):
        """Allow serializers to assign 'fields_to_expand' later (e.g. in bind())."""
        self._fields_to_expand = fields

    @property
    def expanded_fields(self) -> List[EmbeddedFieldMatch]:
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
        """Allow to override the ``results_field`` on construction"""
        super().__init__(*args, **kwargs)
        if results_field:
            self.results_field = results_field
        elif not self.results_field:
            self.results_field = self.child.Meta.model._meta.model_name

    def bind(self, field_name, parent):
        super().bind(field_name, parent)

        # Correct what many_init() did earlier. When the list is not the top-level,
        # but a deeper object (e.g. M2M relation), the fields_to_expand should be
        # known to the child subclass so it can perform expands itself.
        # This list wrapper will not perform the expands in such case.
        if self.root is not self and self.fields_to_expand is not empty:
            self.child.fields_to_expand = self.fields_to_expand

    @cached_property
    def expanded_fields(self) -> List[EmbeddedFieldMatch]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        expand_scope = self.fields_to_expand
        if not expand_scope:
            return []

        if (
            not request.accepted_renderer.supports_list_embeds
            and not request.accepted_renderer.supports_inline_embeds
        ):
            raise ParseError("Embedding objects is not supported for this output format")

        return get_expanded_fields_by_scope(
            self.child,
            expand_scope,
            allow_m2m=request.accepted_renderer.supports_m2m,
        )

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


class DSOModelListSerializer(DSOListSerializer):
    """Perform object embedding for lists.

    This subclass implements the ORM-specific bits that the :class:`DSOListSerializer`
    can't provide.

    This should be used together with the DSO...Pagination class when results are paginated.
    It outputs the ``_embedded`` section for the HAL-JSON spec:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    # Fetcher function to be overridden by subclasses if needed
    id_based_fetcher = None

    def get_prefetch_lookups(self) -> List[Union[models.Prefetch, str]]:
        """Tell which fields should be included for a ``prefetch_related()``."""
        lookups = []

        def _walk_serializer_lookups(serializer, prefix=""):
            # Recursively find all lookups that need to be added.
            for f in serializer.fields.values():
                if f.source != "*" and isinstance(
                    f, (serializers.Serializer, serializers.RelatedField)
                ):
                    lookup = f"{prefix}{f.source.replace('.', '__')}"
                    lookups.append(lookup)

                    if isinstance(f, serializers.Serializer):
                        _walk_serializer_lookups(f, prefix=f"{f.source}__")

        _walk_serializer_lookups(self.child)
        return lookups

    def to_representation(self, data):
        """Improved list serialization.

        * It includes the data for the HAL "_embedded" section.
        * It reads the database with a streaming iterator to reduce memory.
        * It collects any embedded sections, and queries them afterwards
        """
        if self.root is not self or not isinstance(data, models.QuerySet):
            # When generating as part of an sub-object, just output the list.
            return super().to_representation(data)

        request = self.context["request"]

        # Find the the best approach to iterate over the results.
        if prefetch_lookups := self.get_prefetch_lookups():
            # When there are related fields, avoid an N-query issue by prefetching.
            # ChunkedQuerySetIterator makes sure the queryset is still read in partial chunks.
            queryset_iterator = ChunkedQuerySetIterator(data.prefetch_related(*prefetch_lookups))
        else:
            queryset_iterator = data.iterator()

        # Find the desired output format
        if not request.accepted_renderer.supports_list_embeds:
            # When the output format needs a plain list (a non-JSON format), give it just that.
            # The generator syntax still tricks DRF into reading the source bit by bit,
            # without caching the whole queryset into memory.
            items = (self.child.to_representation(item) for item in queryset_iterator)

            # Make sure the first to_representation() is called early on. This makes sure
            # DSOModelSerializer.to_representation() can inspect the CRS, and define the
            # HTTP header for the Content-Crs setting. This will be too late when the streaming
            # rendering started. As bonus, it's a good guard against database errors, since those
            # exceptions might not be nicely rendered either once streaming started.
            _, items = peek_iterable(items)
            return items
        else:
            # Output renderer supports embedding.
            # Add any HAL-style sideloading if these were requested
            embedded_fields = {}
            if self.expanded_fields:
                # All embedded result sets are updated during the iteration over
                # the main data with the relevant ID's to fetch on-demand.
                embedded_fields = {
                    expand_match.name: EmbeddedResultSet(
                        expand_match.field, serializer=expand_match.embedded_serializer
                    )
                    for expand_match in self.expanded_fields
                }

                # Wrap the main object inside an observer, which notifies all
                # embedded sets about the retrieved objects. They prepare their
                # data retrieval accordingly.
                queryset_iterator = ObservableIterator(
                    queryset_iterator,
                    observers=[
                        result_set.inspect_instance for result_set in embedded_fields.values()
                    ],
                )

            # The generator/peek logic avoids unnecessary memory usage (see details above).
            items = (self.child.to_representation(item) for item in queryset_iterator)
            _, items = peek_iterable(items)

            # DSO always mandates a dict structure for JSON responses: {"objectname": [...]}
            return {self.results_field: items, **embedded_fields}


class DSOSerializer(_SideloadMixin, serializers.Serializer):
    """Basic non-model serializer logic.

    This class implements all logic that can be used by all serializers,
    including those which are not based on database models:

    * Geometry values are converted into a single coordinate reference system.
    * The ``?_fields`` parameter can limit the returned fields.
    * ``request.response_content_crs`` is filled with the used CRS value.

    The geometry values are transformed using the :class:`~rest_framework_dso.crs.CRS`
    object found in ``request.accept_crs``.
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
        # Not passing explicit 'fields_to_expand' to the child,
        # only the list needs to handle this information.
        fields_to_expand = kwargs.pop("fields_to_expand", empty)

        # Taken from base method
        child_serializer = cls(*args, **kwargs)
        list_kwargs = {
            "child": child_serializer,
            "fields_to_expand": fields_to_expand,
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

        # Adjust the serializer based on the request,
        # remove fields if a subset is requested.
        request_fields = request.GET.get(self.fields_param)
        if not request_fields and "fields" in request.GET:
            request_fields = request.GET["fields"]  # DSO 1.0

        if request_fields:
            display_fields = self.get_fields_to_display(fields, request_fields)
            fields = OrderedDict(
                [
                    (field_name, field)
                    for field_name, field in fields.items()
                    if field_name in display_fields
                ]
            )

        # Allow embedded objects to be included inline, if this is needed for the output renderer
        # (e.g. CSV). To achieve this effect, the serializers are included as regular fields.
        # The getattr() is needed for the OpenAPIRenderer which lacks the supports_* attrs.
        if getattr(request.accepted_renderer, "supports_inline_embeds", False):
            for embed_match in self.expanded_fields:
                # Not using field.get_serialize() as the .bind() will be called by DRF here.
                name = embed_match.name
                source = embed_match.field.source if embed_match.field.source != name else None
                fields[name] = embed_match.field.serializer_class(
                    source=source, fields_to_expand=None
                )

        return fields

    def get_fields_to_display(self, fields, request_fields) -> set:
        """Tell which fields should be displayed"""

        # Split into fields to include and fields to omit (-fieldname).
        display_fields, omit_fields = set(), set()
        for field in request_fields.split(","):
            if field.startswith("-"):
                omit_fields.add(field[1:])
            else:
                display_fields.add(field)

        if display_fields and omit_fields:
            raise ValidationError(
                "It's not possible to combine inclusions and exclusions in the _fields parameter"
            )

        fields = set(fields.keys())
        if omit_fields:
            display_fields = fields - omit_fields
            invalid_fields = omit_fields - fields
        else:
            invalid_fields = display_fields - fields

        if invalid_fields:
            # Some of `display_fields` are not in result.
            raise ValidationError(
                "'{}' not among the available options".format("', '".join(sorted(invalid_fields))),
                code="fields",
            )
        return display_fields

    @cached_property
    def expanded_fields(self) -> List[EmbeddedFieldMatch]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        expand_scope = self.fields_to_expand
        if not expand_scope:
            return []

        if (
            not request.accepted_renderer.supports_detail_embeds
            and not request.accepted_renderer.supports_inline_embeds
        ):
            raise ParseError("Embedding objects is not supported for this output format")

        return get_expanded_fields_by_scope(
            self, expand_scope, allow_m2m=request.accepted_renderer.supports_m2m
        )

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
        """Check whether the geofields need to be transformed.

        This method also sets ``request.response_content_crs`` so the response rendering
        can tell which Coordinate Reference System is used by all geometry fields.
        """
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
                geo_value = instance.get(field.source)
            else:
                # ModelSerializer
                geo_value = getattr(instance, field.source)

            if geo_value is not None:
                # NOTE: if the same object uses multiple geometries
                # with a different SRID's, this ignores such case.
                return CRS.from_srid(geo_value.srid)

        return None


class DSOModelSerializer(DSOSerializer, serializers.HyperlinkedModelSerializer):
    """DSO-compliant serializer for Django models.

    This serializer can be used inside a list (by :class:`DSOModelListSerializer`
    when ``many=True`` is given), or standalone for a detail page.

    This supports the following extra's:

    * The self-URL is generated in a ``_links`` section.
    * Embedded relations are returned in an ``_embedded`` section.

    To use the embedding feature, include an ``EmbeddedField`` field in the class::

        class SomeSerializer(HALEmbeddedSerializer):
            embedded_field = EmbeddedField(SerializerClass)

            class Meta:
                model = ...
                fields = [...]

    The embedded support works on ``ForeignKey`` fields.
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

    #: Define the field name inside the URL object.
    url_field_name = "self"

    #: Define the object that renders the object URL (e.g. ``_links``).
    serializer_url_field = LinksField

    #: Fetcher function for embedded objects, can be redefined by subclasses.
    id_based_fetcher = None

    def _include_embedded(self):
        """Determines if the _embedded field must be generated."""
        return self.root is self or self.has_fields_to_expand_override()

    def to_representation(self, instance):
        """Check whether the geofields need to be transformed."""
        ret = super().to_representation(instance)

        # See if any HAL-style sideloading was requested
        if self._include_embedded() and self.expanded_fields:
            ret[self.expand_field] = self._get_expand(instance, self.expanded_fields)

        return ret

    def _get_expand(self, instance, expanded_fields: List[EmbeddedFieldMatch]):
        """Generate the expand section for a detail page.

        This reuses the machinery for a list processing,
        but immediately fetches the results as these are inlined in the detail object.
        """
        expanded = {}
        for embed_match in expanded_fields:
            # This just reuses the machinery for listings
            result_set = EmbeddedResultSet(
                embed_match.field,
                serializer=embed_match.embedded_serializer,
                main_instances=[instance],
            )

            if not embed_match.field.is_array:
                # Single object, embed as dict directly
                expanded[embed_match.name] = next(iter(result_set), None)
            else:
                # M2M relation, include as list (no need to delay this).
                expanded[embed_match.name] = list(result_set)

        return expanded
