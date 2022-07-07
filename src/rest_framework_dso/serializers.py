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
import logging
from typing import Generator, Iterable, Optional, Union, cast

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.gdal import GDALException
from django.db import models
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework.exceptions import ParseError
from rest_framework.fields import URLField, empty
from rest_framework.serializers import BaseSerializer
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_gis.fields import GeometryField

from rest_framework_dso import fields
from rest_framework_dso.crs import CRS
from rest_framework_dso.embedding import (
    ChunkedQuerySetIterator,
    EmbeddedFieldMatch,
    EmbeddedResultSet,
    ExpandScope,
    ObservableIterator,
    get_serializer_lookups,
)
from rest_framework_dso.exceptions import HumanReadableGDALException
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable

logger = logging.getLogger(__name__)


class ExpandableSerializer(BaseSerializer):
    """A serializer class that handles ?_expand / ?_expandScope parameters.

    This is a separate class because the parameter needs to be handled
    in 2 separate classes: :class:`DSOListSerializer` and the regular :class:`DSOSerializer`.

    This class can be added as a mixin in case the serializer
    should be a ``ModelSerializer`` or ``ListSerializer``.
    """

    expand_all_param = "_expand"
    expand_param = "_expandScope"  # so ?_expandScope=.. gives a result
    expand_field = "_embedded"  # with _embedded in the result

    def __init__(self, *args, fields_to_expand=empty, **kwargs):
        super().__init__(*args, **kwargs)
        self._expand_scope = fields_to_expand

    def has_expand_scope_override(self) -> bool:
        """Tell whether the 'fields_to_expand' is set by the code instead of request."""
        return self._expand_scope is not empty

    @cached_property
    def is_toplevel(self):
        """Tell whether the current serializer is the top-level serializer.
        Nested serializers shouldn't handle request-parsing logic.
        """
        # The extra parent check tests for serializers that are initialized with many=True
        root = self.root
        return (self is root) or (
            isinstance(self.parent, serializers.ListSerializer) and self.parent is root
        )

    @property
    def expand_scope(self) -> ExpandScope:
        """Retrieve the requested expand.
        For the top-level serializer the request is parsed.
        Deeper nested serializers only return expand information when
        this is explicitly provided by their parent serializer.
        """
        if self._expand_scope is not empty:
            # Instead of retrieving this from request,
            # the expand can be defined using the serializer __init__.
            if isinstance(self._expand_scope, ExpandScope):
                # Typically when nested embedding happens, results are provided beforehand.
                return self._expand_scope
            else:
                # List of fields, given via __init__, typically via unit tests
                return ExpandScope(expand_scope=cast(list, self._expand_scope))
        elif self.is_toplevel:
            # This is the top-level serializer. Parse from request
            request = self.context["request"]
            return ExpandScope(
                expand=request.GET.get(self.expand_all_param),
                expand_scope=request.GET.get(self.expand_param),
            )
        else:
            # Sub field should have received it's fields_to_expand override via __init__().
            # This exists for consistency with DSOListSerializer.to_representation() behavior.
            return ExpandScope()

    @expand_scope.setter
    def expand_scope(self, scope: ExpandScope):
        """Allow serializers to assign expanded fields.
        This is used among others for nested expanding.
        """
        self._expand_scope = scope

    @property
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        """Retrieve the embedded fields for this request."""
        raise NotImplementedError("child serializer should implement this")

    @property
    def field_name_prefix(self) -> str:
        """For debugging, give the fully dotted field name."""
        serializer = self
        path = [""]  # end with dot
        while serializer is not None:
            if serializer.field_name:  # is empty for ListSerializer
                path.append(serializer.field_name)
            serializer = serializer.parent

        return ".".join(reversed(path)) if len(path) > 1 else ""

    @classmethod
    def get_embedded_field(cls, field_name, prefix="") -> fields.AbstractEmbeddedField:
        """Retrieve an embedded field from the serializer class."""
        embedded_fields = getattr(cls.Meta, "embedded_fields", {})
        try:
            return embedded_fields[field_name]
        except KeyError:
            msg = f"Eager loading is not supported for field '{prefix}{field_name}'"
            if embedded_fields:
                available = f", {prefix}".join(sorted(embedded_fields.keys()))
                msg = f"{msg}, available options are: {prefix}{available}"
            raise ParseError(msg) from None

    def get_embedded_objects_by_id(
        self, embedded_field: fields.AbstractEmbeddedField, id_list: list[Union[str, int]]
    ) -> Union[models.QuerySet, Iterable[models.Model]]:
        """Retrieve a number of embedded objects by their identifier.

        While the embedded field typically collects the related objects by
        their primary key, the reverse and M2M field types use a custom identifier
        to find the related objects through a different/reverse relationship.

        This method can be overwritten to support other means of object retrieval,
        e.g. fetching the objects from a remote endpoint. When an queryset is
        returned, it will be optimized to run most efficiently with relationships.
        """
        # Use standard Django foreign-key like behavior.
        # The ID field can be overwritten by the embedded field.
        # This allows to retrieve reverse relations and M2M objects through foreign keys.
        id_field = embedded_field.related_id_field or "pk"
        return embedded_field.related_model.objects.filter(**{f"{id_field}__in": id_list})

    def __init_subclass__(cls, **kwargs):
        """Initialize the embedded field to have knowledge of this class instance.
        This is only needed when the embedded fields were not defined as class attributes,
        but were directly loaded in Meta.embedded_fields. Otherwise, __set_name__
        already did the binding.
        """
        super().__init_subclass__(**kwargs)
        if issubclass(cls, serializers.ListSerializer) or not hasattr(cls, "Meta"):
            return

        embedded_fields = getattr(cls.Meta, "embedded_fields", {})
        for name, embedded_field in embedded_fields.items():
            if embedded_field.field_name is None:
                embedded_field.bind(cls, name)


class DSOListSerializer(ExpandableSerializer, serializers.ListSerializer):
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
        if self.root is not self and self._expand_scope is not empty:
            self.child.expand_scope = self.expand_scope

    @cached_property
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        expand_scope = self.expand_scope
        if not expand_scope:
            return []

        if (
            not request.accepted_renderer.supports_list_embeds
            and not request.accepted_renderer.supports_inline_embeds
        ):
            raise ParseError("Embedding objects is not supported for this output format")

        return expand_scope.get_expanded_fields(
            self.child,
            allow_m2m=request.accepted_renderer.supports_m2m,
            prefix=self.field_name_prefix,
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

    def get_prefetch_lookups(self) -> list[Union[models.Prefetch, str]]:
        """Tell which fields should be included for a ``prefetch_related()``."""
        return get_serializer_lookups(self)

    def to_representation(self, data):
        """Improved list serialization.

        * It includes the data for the HAL "_embedded" section.
        * It reads the database with a streaming iterator to reduce memory.
        * It collects any embedded sections, and queries them afterwards
        """
        request = self.context["request"]

        if getattr(request, "accepted_media_type", None) == "text/html":
            # HTML page does not need data.
            return []
        elif self.root is not self or not isinstance(data, models.QuerySet):
            # Sub-object listing or raw data, just output that.
            return super().to_representation(data)
        elif not request.accepted_renderer.supports_list_embeds:
            # Root level, but output format needs a list. Give a generator-based one.
            return self._as_generator(data)
        else:
            # Root-level, output dict with embeds
            return self._as_hal_with_embeds(data)

    def get_queryset_iterator(self, queryset: models.QuerySet) -> Iterable[models.Model]:
        """Get the most optimal iterator to traverse over a queryset."""
        # Find the best approach to iterate over the results.
        if prefetch_lookups := self.get_prefetch_lookups():
            # When there are related fields, avoid an N-query issue by prefetching.
            # ChunkedQuerySetIterator makes sure the queryset is still read in partial chunks.
            # NOTE: this is no longer needed starting with Django 4.1+
            return ChunkedQuerySetIterator(queryset.prefetch_related(*prefetch_lookups))
        else:
            return queryset.iterator()

    def _as_generator(self, data: models.QuerySet) -> Generator[models.Model, None, None]:
        """The list output as a plain generator."""
        # When the output format needs a plain list (a non-JSON format), give it just that.
        # The generator syntax still tricks DRF into reading the source bit by bit,
        # without caching the whole queryset into memory.
        queryset_iterator = self.get_queryset_iterator(data)
        items = (self.child.to_representation(item) for item in queryset_iterator)

        # Make sure the first to_representation() is called early on. This makes sure
        # DSOModelSerializer.to_representation() can inspect the CRS, and define the
        # HTTP header for the Content-Crs setting. This will be too late when the streaming
        # rendering started. As bonus, it's a good guard against database errors, since those
        # exceptions might not be nicely rendered either once streaming started.
        _, items = peek_iterable(items)
        return items

    def _as_hal_with_embeds(self, data: models.QuerySet) -> dict:
        """The list is generated as dictionary with sections for the embeds."""
        queryset_iterator = self.get_queryset_iterator(data)

        # Output renderer supports embedding.
        # Add any HAL-style sideloading if these were requested
        embedded_fields = {}
        if self.expanded_fields:
            # All embedded result sets are updated during the iteration over
            # the main data with the relevant ID's to fetch on-demand.
            fields_to_display = self.child.fields_to_display
            embedded_fields = {
                expand_match.name: EmbeddedResultSet.from_match(expand_match)
                for expand_match in self.expanded_fields
                if fields_to_display.allow_nested(expand_match.name)
            }

            # Wrap the main object inside an observer, which notifies all
            # embedded sets about the retrieved objects. They prepare their
            # data retrieval accordingly.
            queryset_iterator = ObservableIterator(
                queryset_iterator,
                observers=[result_set.inspect_instance for result_set in embedded_fields.values()],
            )

        # The generator/peek logic avoids unnecessary memory usage (see details above).
        items = (self.child.to_representation(item) for item in queryset_iterator)
        _, items = peek_iterable(items)

        # DSO always mandates a dict structure for JSON responses: {"objectname": [...]}
        return {self.results_field: items, **embedded_fields}


class DSOSerializer(ExpandableSerializer, serializers.Serializer):
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

    fields_always_included = {"_links"}

    def __init__(self, *args, fields_to_display=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fields_to_display = fields_to_display

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

    @property
    def fields_to_display(self) -> fields.FieldsToDisplay:
        """Define which fields should be included only."""
        if isinstance(self._fields_to_display, fields.FieldsToDisplay):
            # Typically when nested embedding happens, results are provided beforehand.
            # This also returns cached data if the previous flow was called before.
            return self._fields_to_display

        # Lazy evaluation of the current state to create the object:
        if self._fields_to_display is not None:
            # A different value was passed via __init__() e.g. via unit tests or a sub-serializer
            self._fields_to_display = fields.FieldsToDisplay(
                cast(list[str], self._fields_to_display)
            )
        elif self.is_toplevel:
            # This is the top-level serializer. Parse from request
            request = self.context["request"]
            request_fields = request.GET.get(self.fields_param)
            if not request_fields and "fields" in request.GET:
                request_fields = request.GET["fields"]  # DSO 1.0

            self._fields_to_display = fields.FieldsToDisplay(
                request_fields.split(",") if request_fields else None
            )
        else:
            # Nested serializer. Take from parent
            parent = self.parent
            if isinstance(parent, (serializers.ListSerializer, serializers.ListField)):
                parent = parent.parent

            self._fields_to_display = parent.fields_to_display.as_nested(self.field_name)

        return self._fields_to_display

    @fields_to_display.setter
    def fields_to_display(self, fields_to_display: fields.FieldsToDisplay):
        """Allow serializers to assign 'fields_to_expand' later (e.g. in bind())."""
        self._fields_to_display = fields_to_display

    def get_fields(self) -> dict[str, serializers.Field]:
        """Override DRF logic so fields can be removed from the response.

        When looking deeper inside DRF logic, you'll find that ``get_fields()`` makes
        a deepcopy of ``self._declared_fields``. This approach allows making changes to the
        statically defined fields on this serializer instance. Only once all fields are created,
        the mapping is assigned to self.fields and ``field.bind()`` is called on each field.
        At that point, the fields know their own field name and serializer parent.

        Omitting a field from the serializer is the most efficient way to avoid returning data,
        since the serializer won't query/format the data at all. This may also avoid
        additional queries in case of relational fields.
        """
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
        fields = self.limit_return_fields(fields)

        # Allow embedded objects to be included inline, if this is needed for the output renderer
        # (e.g. CSV). To achieve this effect, the serializers are included as regular fields.
        # The getattr() is needed for the OpenAPIRenderer which lacks the supports_* attrs.
        if getattr(request.accepted_renderer, "supports_inline_embeds", False):
            for embed_match in self.expanded_fields:
                if not self.fields_to_display.allow_nested(embed_match.name):
                    continue

                # Not using field.get_serializer() as the .bind() will be called by DRF here.
                name = embed_match.name
                source = embed_match.field.source if embed_match.field.source != name else None
                fields[name] = embed_match.field.serializer_class(
                    source=source,
                    fields_to_expand=None,
                    fields_to_display=self.fields_to_display.as_nested(name),
                )

        return fields

    def limit_return_fields(
        self, fields: dict[str, serializers.Field]
    ) -> dict[str, serializers.Field]:
        """Tell which fields should be included in the response.
        Any field that is omitted will not be outputted, nor queried.
        """
        if fields_to_display := self.fields_to_display:  # also checks is_empty
            fields = fields_to_display.apply(
                fields,
                valid_names=self.get_valid_field_names(fields),
                always_keep=self.fields_always_included,
            )

        return fields

    def get_valid_field_names(self, fields: dict[str, serializers.Field]) -> set[str]:
        """Tell which fields are valid to use in the ``?_fields=..`` query.
        This returns additional entries for relationships and expandable (virtual)fields,
        as these should not trigger error messages when those names are mentioned.
        """
        return {f.name for f in self.expanded_fields} | set(fields.keys())

    @cached_property
    def expanded_fields(self) -> list[EmbeddedFieldMatch]:
        """Retrieve the embedded fields for this serializer"""
        request = self.context["request"]
        expand_scope = self.expand_scope
        if not expand_scope:
            return []

        if (
            not request.accepted_renderer.supports_detail_embeds
            and not request.accepted_renderer.supports_inline_embeds
        ):
            raise ParseError("Embedding objects is not supported for this output format")

        return expand_scope.get_expanded_fields(
            self,
            allow_m2m=request.accepted_renderer.supports_m2m,
            prefix=self.field_name_prefix,
        )

    @cached_property
    def _geometry_fields(self) -> list[GeometryField]:
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
    def _url_content_fields(self) -> list[URLField]:
        """indicates if model contains a URLField type so the content can be URL encoded"""
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
        is_dict = isinstance(instance, dict)  # happens with remote API proxy responses
        for field in self._geometry_fields:
            geo_value = instance[field.source] if is_dict else getattr(instance, field.source)
            if geo_value is not None:
                try:
                    accept_crs.apply_to(geo_value)
                except GDALException as e:
                    # While there could be various reasons for this, the most common one
                    # is that the data has coordinates outside the projected bounds of the CRS.
                    # Instead rendering /* Aborted by GDALException during rendering! */ this
                    # exception message points the user directly to the data supplier.
                    raise HumanReadableGDALException(
                        "Fout tijdens coördinaatconversie voor"
                        f" {instance._meta.model_name} #{instance.pk}."
                        " Neem a.u.b. contact op met de bronhouder van deze data"
                        " om dit probleem op te lossen."
                    ) from e

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

    * The self-URL can be generated when this serializer is used for a ``_links`` section.
    * Embedded relations are returned in an ``_embedded`` section.

    To use the embedding feature, include an ``EmbeddedField`` field in the class::

        class SomeSerializer(DSOModelSerializer):
            embedded_field = EmbeddedField(SerializerClass)

            class Meta:
                model = ...
                fields = [...]

    The embedded support works on all relational fields.
    """

    _default_list_serializer_class = DSOModelListSerializer
    serializer_field_mapping = {
        **serializers.HyperlinkedModelSerializer.serializer_field_mapping,
        # Override the URL field
        models.URLField: fields.DSOURLField,
        # Override what django_rest_framework_gis installs in the app ready() signal:
        gis_models.GeometryField: fields.DSOGeometryField,
        gis_models.PointField: fields.DSOGeometryField,
        gis_models.LineStringField: fields.DSOGeometryField,
        gis_models.PolygonField: fields.DSOGeometryField,
        gis_models.MultiPointField: fields.DSOGeometryField,
        gis_models.MultiLineStringField: fields.DSOGeometryField,
        gis_models.MultiPolygonField: fields.DSOGeometryField,
        gis_models.GeometryCollectionField: fields.DSOGeometryField,
    }

    #: Define that having an unknown field named "self" will be rendered as a hyperlink
    # to this object, using a field class that output a {"href": ..., "title": ...} structure.
    url_field_name = "self"
    serializer_url_field = fields.DSOSelfLinkField

    #: Define that relations will also be generated as {"href": ..., "title": ...}.
    serializer_related_field = fields.DSORelatedLinkField

    def _include_embedded(self):
        """Determines if the _embedded field must be generated."""
        return self.root is self or self.has_expand_scope_override()

    def to_representation(self, instance):
        """Check whether the geofields need to be transformed."""
        ret = super().to_representation(instance)

        # See if any HAL-style sideloading was requested
        # This only happens for nested fields, or when this serializer
        # is the top-level serializer (meaning it's a detail view).
        if self._include_embedded() and self.expanded_fields:
            ret[self.expand_field] = self._get_expand(instance, self.expanded_fields)

        return ret

    def _get_expand(self, instance, expanded_fields: list[EmbeddedFieldMatch]):
        """Generate the expand section for a detail page.

        This reuses the machinery for a list processing,
        but immediately fetches the results as these are inlined in the detail object.
        """
        expanded = {}
        for embed_match in expanded_fields:
            # As optimization, try resolving the object via prefetches.
            # This is needed when the serializer data is fetched for a listing.
            prefetched_value = self._get_prefetched_expand(
                instance,
                lookup=embed_match.field.source,
                is_m2m_field=embed_match.field.is_array,
            )
            if prefetched_value is not empty:
                expanded[embed_match.name] = (
                    embed_match.embedded_serializer.to_representation(prefetched_value)
                    if prefetched_value is not None
                    else None
                )
                continue

            # This just reuses the machinery for listings
            result_set = EmbeddedResultSet.from_match(embed_match)
            result_set.inspect_instance(instance)

            logger.debug("Fetching embedded field: %s", embed_match.full_name)
            if not embed_match.field.is_array:
                # Single object, embed as dict directly
                expanded[embed_match.name] = next(iter(result_set), None)
            else:
                # M2M relation, include as list (no need to delay this).
                expanded[embed_match.name] = list(result_set)

        return expanded

    def _get_prefetched_expand(self, instance, lookup, is_m2m_field):
        # First try resolving the object via prefetches.
        if not is_m2m_field:
            # Prefetched foreign keys are stored in model._state.fields_cache.
            return instance._state.fields_cache.get(lookup, empty)
        elif prefetched_m2m := getattr(instance, "_prefetched_objects_cache", None):
            # Prefetched M2M are stored in a ._prefetched_objects_cache
            return prefetched_m2m.get(lookup, empty)
        else:
            return empty


class HALLooseLinkSerializer(serializers.Serializer):
    """This is an empty class that is used to type a _links subfield
    as a loose relation. This information is necessary to determine the
    runtime behavior of the serializer object structure, for example
    when resolving the prefetch lookups for a queryset."""
