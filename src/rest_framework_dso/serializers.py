from collections import OrderedDict
from typing import List, Union, cast, Optional

from django.db import models
from django.utils.functional import cached_property
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import empty
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_gis.fields import GeometryField

from rest_framework_dso.crs import CRS
from rest_framework_dso.utils import EmbeddedHelper


class _SideloadMixin:
    expand_param = "expand"  # so ?expand=.. gives a result
    expand_field = "_embedded"  # with _embedded in the result

    def __init__(self, *args, fields_to_expand=empty, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields_to_expand = fields_to_expand

    def get_fields_to_expand(self) -> Union[list, bool]:
        if self.fields_to_expand is not empty:
            return cast(list, self.fields_to_expand)
        # model = self.context["view"].serializer_class.Meta.model

        # Initialize from request
        expand = self.context["request"].GET.get(self.expand_param)
        if expand == "true":
            # ?expand=true should export all fields
            return True
        elif expand:
            # otherwise, parse as a list of fields to expand.
            return expand.split(",")
        else:
            return False


class _LinksField(serializers.HyperlinkedIdentityField):
    """Internal field to generate the _links bit"""

    def to_representation(self, value):
        request = self.context.get("request")
        return {
            "self": {
                "href": self.get_url(value, self.view_name, request, None),
                "title": str(value),
            },
        }


class DSOListSerializer(_SideloadMixin, serializers.ListSerializer):
    """Perform object embedding for lists.

    This should be used together with the DSO...Pagination class when results are paginated.
    It outputs the ``_embedded`` section for the HAL-JSON spec:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    #: The field name for the results envelope
    results_field = None

    def __init__(self, *args, results_field=None, **kwargs):
        super().__init__(*args, **kwargs)
        if results_field:
            self.results_field = results_field
        elif not self.results_field:
            self.results_field = self.child.Meta.model._meta.model_name

    @property
    def data(self):
        ret = super(serializers.ListSerializer, self).data
        if isinstance(ret, dict):
            # Override to make sure dict is preserved
            return ReturnDict(ret, serializer=self)
        else:
            # Normal behavior
            return ReturnList(ret, serializer=self)

    def to_representation(self, data):
        # Taken this part from ListSerializer.to_representation()
        # to avoid  accessing 'data.all()' twice, causing double evaluations.
        iterable = data.all() if isinstance(data, models.Manager) else data

        items = [self.child.to_representation(item) for item in iterable]

        # Only when we're the root structure, consider returning a dictionary.
        # When acting as a child list somewhere, embedding never happens.
        if self.root is self:
            # See if any HAL-style sideloading was requested

            expand = self.get_fields_to_expand()
            embeds = {}
            if expand and items:
                request = self.context.get("request")
                auth_checker = (
                    getattr(request, "is_authorized_for", None) if request else None
                )
                embed_helper = EmbeddedHelper(
                    self.child, expand=expand, auth_checker=auth_checker
                )
                embeds = embed_helper.get_list_embedded(iterable)
                if embeds:
                    # Provide the _embedded section, that DSO..Paginator classes wrap.
                    return {self.results_field: items, **embeds}
            return {self.results_field: items, **embeds}

        return items


class DSOSerializer(_SideloadMixin, serializers.HyperlinkedModelSerializer):
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

    # Make sure the _links bit is generated:
    url_field_name = "_links"
    serializer_url_field = _LinksField

    fields_param = "fields"  # so ?fields=.. gives a result

    @classmethod
    def many_init(cls, *args, **kwargs):
        """The initialization for many=True.

        This overrides the default ``list_serializer_class`` so it
        also returns HAL-style embedding.
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
            meta, "list_serializer_class", DSOListSerializer
        )

        # results field uses model_name if possiblee.
        list_kwargs["results_field"] = getattr(meta, "many_results_field", None)

        return list_serializer_class(*args, **list_kwargs)

    def get_fields_to_display(self):
        request = self.context.get("request")
        if request is not None:
            fields = request.GET.get(self.fields_param)
            if fields:
                display_fields = fields.split(",")

                if not (set(display_fields) <= set(self.fields.keys())):
                    # Some of `display_fields` are not in result.
                    invalid_fields = [
                        field_name
                        for field_name in display_fields
                        if field_name not in self.fields
                    ]
                    raise ValidationError(
                        "'{}' is not one of available options".format(
                            ", ".join(invalid_fields)
                        ),
                        code="fields",
                    )
                return display_fields
        return None

    @cached_property
    def _geometry_fields(self) -> List[GeometryField]:
        # Allow classes to exclude fields (e.g. a "point_wgs84" field shouldn't be used.)
        exclude_crs_fields = getattr(self.Meta, "exclude_crs_fields", ())
        return [
            field
            for name, field in self.fields.items()
            if isinstance(field, GeometryField)
            and field.field_name not in exclude_crs_fields
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

        display_fields = self.get_fields_to_display()
        if display_fields is not None:
            # Limit result to requested fields only
            self.fields = OrderedDict(
                [
                    (field_name, field)
                    for field_name, field in self.fields.items()
                    if field_name in display_fields
                ]
            )

        ret = super().to_representation(instance)

        # See if any HAL-style sideloading was requested
        if not hasattr(self, "parent") or self.root is self:
            expand = self.get_fields_to_expand()
            if expand:
                request = self.context.get("request")
                auth_checker = (
                    getattr(request, "is_authorized_for", None) if request else None
                )
                embed_helper = EmbeddedHelper(
                    self, expand=expand, auth_checker=auth_checker
                )
                ret[self.expand_field] = embed_helper.get_embedded(instance)

        return ret

    def _apply_crs(self, instance, accept_crs: CRS):
        """Make sure all geofields use the same CRS."""
        for field in self._geometry_fields:
            geo_value = getattr(instance, field.source)
            if geo_value is not None:
                accept_crs.apply_to(geo_value)

    def _get_crs(self, instance) -> Optional[CRS]:
        """Find the used CRS in the geometry field(s)."""
        for field in self._geometry_fields:
            geo_value = getattr(instance, field.source)
            if geo_value is not None:
                # NOTE: if the same object uses multiple geometries
                # with a different SRID's, this ignores such case.
                return CRS.from_srid(geo_value.srid)

        return None
