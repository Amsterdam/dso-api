from __future__ import annotations

from collections.abc import Iterable
from typing import cast
from urllib.parse import quote, urlsplit, urlunsplit

from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.utils.functional import cached_property
from django.utils.translation import ngettext
from more_itertools import first
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework_gis.fields import GeometryField
from schematools.contrib.django.models import LooseRelationField
from schematools.types import DatasetFieldSchema

from rest_framework_dso.utils import group_dotted_names, unlazy_object

DictOfDicts = dict[str, dict[str, dict]]


class FieldsToDisplay:
    """Tell which fields should be displayed in the response.

    This object type helps to track nesting levels of fields to render,
    e.g. ``?_fields=id,code,customer.id,customer.name``. It also handles
    exclusions across nesting levels, e.g. ``?_fields=-customer.name``.
    """

    def __init__(self, fields: list[str] | None = None, prefix: str = ""):
        # The 'fields' is pre-processed into 3 structures that allow to deal with
        # all possible scenario's that the methods of this class need to cover.
        # For example, this also allows queries like ?_fields=-person.name to properly
        # include the person object, but on the next level exclude the 'name' field,
        # AND also still include all other fields at the top-level (not only include person)
        self._includes: set[str] = set()
        self._excludes: set[str] = set()
        self._children: dict[str, FieldsToDisplay] = {}
        self._allow_all = True
        self.prefix = prefix

        if fields:
            # Parse request string into nested format
            fields = group_dotted_names(fields)

            self._allow_all = False
            self._init_nesting(fields)

    def __repr__(self):
        """Make debugging easier"""
        prefix = f"prefix={self.prefix}, " if self.prefix else ""
        children = sorted(self._children.keys())
        if self._allow_all:
            # no {prefix} here, as it's unreliable due to reused singleton instances.
            return "<FieldsToDisplay: allow all>"
        elif self._excludes:
            return (
                f"<FieldsToDisplay: {prefix}exclude={sorted(self._excludes)!r}"
                f", children={children}>"
            )
        elif not self._includes and self._children:
            # no limitations on the current level, but some excludes on a deeper level
            return f"<FieldsToDisplay: allow all, children={children}>"
        elif self._includes:
            return (
                f"<FieldsToDisplay: {prefix}include={sorted(self._includes)!r}"
                f", children={children}>"
            )
        else:
            return "<FieldsToDisplay: deny all>"

    def reduced(self):
        """Whether the returned fields need to be reduced.
        Note that this returns false when there are child nodes that need to be reduced.
        These are found with :meth:`allow_nested`, :meth:`as_nested` and :attr:`children`.
        """
        return not self._allow_all

    def _init_nesting(self, fields: DictOfDicts, exclude_leaf=False):
        """Split the field parameters to a tree of includes and excludes."""
        self._allow_all = False  # reset for child nodes
        for field, sub_fields in fields.items():
            is_exclude = field.startswith("-")
            name = field[1:] if is_exclude else field

            if sub_fields:
                if any(sub_field.startswith("-") for sub_field in sub_fields):
                    # Avoid ?_fields=person.-name
                    raise ValidationError(
                        "The minus-sign can only be used in front of a field name.", code="fields"
                    )

                # When there are sub fields, always allow the main object.
                # This includes options like ?_fields=-person.name.
                child = self._children.get(name)
                if child is None:
                    # Typically this path is taken, but the same name can occur twice
                    # when an exclude happens on a deeper level.
                    # e.g. ?_fields=person.name=..,-person.dossier.data
                    # The top level has both an "person" and "-person" group.
                    child = FieldsToDisplay(prefix=f"{name}.")
                    self._children[name] = child

                child._init_nesting(sub_fields, exclude_leaf=exclude_leaf or is_exclude)
            else:
                if is_exclude or exclude_leaf:
                    self._excludes.add(name)
                else:
                    self._includes.add(name)

        if self._includes and self._excludes:
            # Already validated before
            raise ValidationError(
                "It's not possible to combine inclusions and exclusions"
                " in the _fields parameter",
                code="fields",
            )

    @property
    def allow_all(self):
        return self._allow_all

    @property
    def includes(self) -> Iterable[str]:
        """Tell which fields must be included.
        Note that any item in :attr:`children` should also be considerd for inclusion.
        """
        return self._includes

    @property
    def excludes(self) -> Iterable[str]:
        """Tell which fields must not be displayed."""
        return self._excludes

    @property
    def children(self) -> Iterable[str]:
        """Tell which sub-objects will have exclusions"""
        return self._children.keys()

    def allow_nested(self, field_name) -> bool:
        """Whether a field can be used for nesting"""
        return (
            self._allow_all
            or field_name in self._children
            or field_name in self._includes
            or (self._excludes and field_name not in self._excludes)
        )

    def as_nested(self, field_name) -> FieldsToDisplay:
        """Return a new instance that starts at a nesting level.
        An empty result is returned when the field does not allow nesting, or isn't mentioned.
        """
        if self._allow_all:
            return ALLOW_ALL_FIELDS_TO_DISPLAY

        try:
            return self._children[field_name]
        except KeyError:
            if self._excludes:
                # When this level perform excludes, deny access if it's excluded
                return (
                    DENY_SUB_FIELDS_TO_DISPLAY
                    if field_name in self._excludes
                    else ALLOW_ALL_FIELDS_TO_DISPLAY
                )
            elif self._includes:
                # When there are explicit includes, deny access if it's missing:
                return (
                    ALLOW_ALL_FIELDS_TO_DISPLAY
                    if field_name in self._includes
                    else DENY_SUB_FIELDS_TO_DISPLAY
                )
            else:
                # No includes/excludes -> this level only has children.
                return ALLOW_ALL_FIELDS_TO_DISPLAY

    def get_allow_list(self, valid_names: set[str]) -> tuple[set[str], set[str]]:
        """Find out which fields should be included.
        This transforms the include/exclude behavior
        into a positive list of fields that should be kept.
        """
        # Detect any invalid names
        if self._allow_all:
            return valid_names, set()
        elif self._excludes:
            fields_to_keep = valid_names - self._excludes
            invalid_fields = self._excludes - valid_names
        elif not self._includes and self._children:
            # Only sub-objects are limited, so the 'include' should not be used
            # for limiting the fields at all.
            return valid_names, set()
        else:
            # The includes list is leading, even when its empty.
            fields_to_keep = set(self._includes)  # copy to avoid tampering
            invalid_fields = fields_to_keep - valid_names

        # To exclude a sublevel attribute, the parent must always be included:
        fields_to_keep.update(self._children.keys())
        return fields_to_keep, invalid_fields

    def apply(
        self,
        fields: dict[str, serializers.Field],
        valid_names: Iterable[str],
        always_keep: Iterable[str],
    ) -> dict[str, serializers.Field]:
        """Reduce the fields from a serializer based on the current context.
        This returns a new dictionary that can be assigned to `serializer.fields`.
        """
        if self._allow_all:
            return fields

        # Split into fields to include and fields to omit (-fieldname).
        valid_names = set(fields.keys()) | set(valid_names)
        fields_to_keep, invalid_fields = self.get_allow_list(valid_names)
        fields_to_keep.update(always_keep)

        if invalid_fields:
            # Some of `display_fields` are not in result.
            names_str = f"', {self.prefix}'".join(sorted(invalid_fields))
            raise ValidationError(
                ngettext(
                    "The following field name is invalid: {names}.",
                    "The following field names are invalid: {names}.",
                    len(invalid_fields),
                ).format(names=f"'{self.prefix}{names_str}'"),
                code="fields",
            )

        # Python 3.6+ dicts are already ordered, so there is no need to use DRF's OrderedDict
        return {
            field_name: field
            for field_name, field in fields.items()
            if field_name in fields_to_keep
        }


ALLOW_ALL_FIELDS_TO_DISPLAY = FieldsToDisplay()
DENY_SUB_FIELDS_TO_DISPLAY = FieldsToDisplay()
DENY_SUB_FIELDS_TO_DISPLAY._allow_all = False


def get_embedded_field_class(
    model_field: RelatedField | ForeignObjectRel,
) -> type[AbstractEmbeddedField]:
    """Return the embedded field type that is suited for a particular model field."""
    if isinstance(model_field, ForeignObjectRel):
        # Reverse relations
        if model_field.many_to_many:
            return EmbeddedManyToManyRelField
        else:
            return EmbeddedManyToOneRelField
    else:
        if model_field.one_to_many or model_field.many_to_many:
            return EmbeddedManyToManyField
        else:
            return EmbeddedField


class AbstractEmbeddedField:
    """A 'virtual' field that contains the configuration of an embedded field.

    Note this virtual field is *not* part of the serializer.fields,
    thus it's also **not** copied per instance. It's not possible to store
    request-state (such as the parent serializer object) in this class.

    There are two ways to include an embedded field in the serializer.
    Either add it as a class attribute (it will auto-register
    in ``Meta.embedded_fields``), or add it directly in ``Meta.embedded_fields``.
    Both styles require the serializer class to inherit
    from :class:`rest_framework_dso.serializers.ExpandableSerializer`.

    The embedded fields are designed to be efficient during streaming rendering
    of large datasets. Instead of collecting/prefetching the whole queryset in one go,
    the required relationship data is incrementally collected as each individual rendered
    object is written to the client. After rendering the whole first list of objects,
    the related objects can now be queried in a single SQL statement and be written
    to the next section in the ``"_embedded": { ... }`` dict.

    Hence, there are 2 significant overrides to implement:
    the :meth:`get_related_ids` method and :attr:`related_id_field` attribute.
    These define how a relationship is queried and should allow spanning FK/M2M
    and reverse ORM relations by playing with those 2 overrides.
    """

    def __init__(
        self,
        serializer_class: type[serializers.Serializer],
        *,
        field_schema: DatasetFieldSchema | None = None,
        source=None,
    ):
        self.serializer_class = serializer_class
        self.source = source

        self.field_name = None
        self.field_schema = field_schema
        self.parent_serializer_class = None

    def __deepcopy__(self, memo):
        # Fix a massive performance hit when DRF performs a deepcopy() of all fields
        result = self.__class__.__new__(self.__class__)
        memo[id(result)] = self
        result.__dict__.update({k: v for k, v in self.__dict__.items() if k != "field_schema"})
        result.field_schema = self.field_schema
        return result

    def __repr__(self):
        try:
            parent_serializer = self.parent_serializer_class.__name__
        except AttributeError:
            parent_serializer = "not bound"
        return (
            f"<{self.__class__.__name__}: {parent_serializer}.{self.field_name},"
            f" {self.serializer_class.__name__}>"
        )

    def __set_name__(self, owner, name):
        self.bind(owner, name)

    def bind(self, parent_serializer_class: type[serializers.Serializer], field_name: str):
        from .serializers import ExpandableSerializer

        if not issubclass(parent_serializer_class, ExpandableSerializer):
            raise TypeError(
                f"{parent_serializer_class} does not extend from DSO serializer classes"
            ) from None

        self.parent_serializer_class = parent_serializer_class
        self.field_name = field_name
        if self.source is None:
            self.source = self.field_name

        # Also register this field in the Meta.embedded,
        # which makes it easier to collect embedded relations
        meta = self.parent_serializer_class.Meta
        if not hasattr(meta, "embedded_fields"):
            meta.embedded_fields = {}
        meta.embedded_fields[field_name] = self

    def get_related_ids(self, instance):
        """Return the "ID" values that are referenced from a single instance
        This can be a FK or an NM relationship.
        """
        raise NotImplementedError()

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        """Build the EmbeddedField serializer object that can generate an embedded result.

        Since this virtual-field object persists between all sessions,
        the parent/root serializer needs to be provided here.
        Settings like ``fields_to_extend`` are provided via the **kwargs.
        """
        if not isinstance(parent, self.parent_serializer_class):
            raise TypeError(f"Invalid parent for {self.__class__.__name__}.get_serializer()")

        # Make sure the serializer is the true object, or other isinstance() checks will fail.
        self.serializer_class = unlazy_object(self.serializer_class)
        embedded_serializer = self.serializer_class(context=parent.context, **kwargs)
        embedded_serializer.bind(field_name=self.source, parent=parent)
        return embedded_serializer

    @cached_property
    def related_model(self) -> type[models.Model]:
        """Return the Django model class"""
        # Make sure the serializer is the true object, or other isinstance() checks will fail.
        self.serializer_class = unlazy_object(self.serializer_class)
        return self.serializer_class.Meta.model

    @property
    def related_id_field(self) -> str | None:
        """The ID field is typically auto-detected.

        It can however be overwritten to change the object retrieval query.
        This is used by reverse relationships to retrieve objects
        from a related foreign key instead.
        """
        return None

    @cached_property
    def parent_model(self) -> type[models.Model]:
        """Return the Django model class"""
        return self.parent_serializer_class.Meta.model

    @cached_property
    def source_field(
        self,
    ) -> RelatedField | models.ForeignObjectRel:
        return self.parent_model._meta.get_field(self.source)

    @cached_property
    def is_loose(self) -> bool:
        """Signals that the relation only links to the first part of a foreign composite key"""
        return isinstance(self.source_field, LooseRelationField)

    @cached_property
    def is_array(self) -> bool:
        """Whether the relation returns an list of items (e.g. ManyToMany)."""
        # This includes ManyToManyField, LooseRelationManyToManyField and ForeignObjectRel
        return self.source_field.many_to_many or self.source_field.one_to_many

    @cached_property
    def is_reverse(self) -> bool:
        """Whether the relation is actually a reverse relationship."""
        return isinstance(self.source_field, ForeignObjectRel)


class EmbeddedField(AbstractEmbeddedField):
    """An embedded field for a foreign-key relation.

    This collects the identifiers to the related foreign objects,
    so these can be queried once all main objects have been written to the client.
    """

    @cached_property
    def attname(self) -> str:
        try:
            # For ForeignKey/OneToOneField this resolves to "{field_name}_id"
            return self.source_field.attname
        except FieldDoesNotExist:
            # Allow non-FK relations, e.g. a "bag_id" to a completely different database
            if not self.source.endswith("_id"):
                return f"{self.source}_id"
            else:
                return self.source

    def get_related_ids(self, instance):
        """Find the _id field value(s)"""
        # The identifier of the foreign objects is known in the parent object. Becomes the query:
        # self.related_model.objects.filter({pk}__in=[ids to foreign instances])
        id_value = getattr(instance, self.attname, None)
        return [] if id_value is None else [id_value]


class EmbeddedManyToOneRelField(EmbeddedField):
    """An embedded field for reverse relations (of foreign keys).

    This collects the identifiers of all primary objects, so any objects
    that link to those primary objects can be resolved afterwards in a single query.

    The name of this object is somewhat awkward, but it follows Django conventions.
    Django ForeignKey's have a OneToManyRel that describes the relationship.
    That object is also placed on the foreign object as reverse field, thus giving the
    funny ``ManyToOneRel.one_to_many == True`` situation. The reverse field should have
    been called something like "OneToManyField" but Django reuses the "ManyToOneRel" there.
    """

    def get_related_ids(self, instance):
        """Reverse relations link to the given instance, hence we track the 'pk'."""
        return [instance.pk]

    @property
    def attname(self) -> str:
        """Reverse relations are based on the current object's identifier."""
        if self.parent_model.is_temporal():
            return first(self.parent_model.table_schema().identifier)
        else:
            return "pk"

    @property
    def related_id_field(self):
        """Change the ID field to implement reverse relations.
        This lets the results be read from the remote foreign key to retrieve the objects.
        """
        # This causes the queryset to be constructed as:
        # self.related_model.objects.filter({fk_field}__in=[ids to primary instances])
        return self.source_field.remote_field.name


class EmbeddedManyToManyField(AbstractEmbeddedField):
    """An embedded field for a M2M relation.

    This collects all identifiers of the primary objects, so the through table
    can be queried afterwards in a single call to find all related objects.
    """

    def get_serializer(self, parent: serializers.Serializer, **kwargs) -> serializers.Serializer:
        kwargs.setdefault("many", True)
        return super().get_serializer(parent, **kwargs)

    def get_related_ids(self, instance):
        """The PK of this source object can be used to find the relation in the through table."""
        return [instance.pk]

    @cached_property
    def related_id_field(self) -> str | None:
        # Given a relation (A -> M2M -> B), this field acts on data of the first model (A).
        # So it collects A.pk, and then needs to resolve instances of B.
        #
        # Instead of using the reverse name of the models.ManyToManyField,
        # it uses the foreign keys inside the through table. This avoids another JOIN to A,
        # only to have it's primary key checked. The basic query looks like:
        #
        #   B.objects.filter({rev_m2m_into_through_table}__{fk_to_a}__in=[idlist])
        #
        # Aka:
        #
        #   self.related_model.objects.filter({reverse_through_field}__{idfield}__in=[PKs])
        #
        m2m_field = cast(models.ManyToManyField, self.source_field)
        return "__".join(
            path_info.join_field.name for path_info in m2m_field.get_reverse_path_info()
        )


class EmbeddedManyToManyRelField(EmbeddedManyToManyField):
    """Embedded field for reverse M2M relations.

    This performs roughly the same query as the forward M2M relation,
    except that the relation to the through table is followed backwards.
    """

    @cached_property
    def related_id_field(self) -> str | None:
        # Given a relation (A -> M2M -> B), this rel-field acts on data from the second model (B).
        # Hence, it collects identifiers from the second relation (B.pk).
        # To retrieve the intended objects (A), the query starts at the first model (A).
        # It then filters using the reverse relation that leads into the M2M table,
        # and then joins with the FK field that corresponds with the second model (M2M.fk_to_B).
        # So you get:
        #
        #   A.objects.filter({rev_m2m_into_through_table}__{fk_of_b}__in=[id list of B])
        #
        # Aka:
        #
        #   self.related_model.objects.filter({rev_m2m_through_field}__{fkfield}__in=[PKs])
        #
        m2m_field = cast(models.ManyToManyField, self.source_field.field)
        return "__".join(path_info.join_field.name for path_info in m2m_field.get_path_info())


class DSORelatedLinkField(serializers.HyperlinkedRelatedField):
    """A field that generates the proper structure of an object in the ``_links`` section.
    This generates a "title" and "href"..
    """


class DSOSelfLinkField(DSORelatedLinkField, serializers.HyperlinkedIdentityField):
    """The link object for a link to 'self'.

    This implementation is solely done by inheritance, as the 'HyperlinkedIdentityField' is
    an 'HyperlinkedRelatedField' underneath with the parameters ``source="*", read_only="True"``.
    """


class DSOGeometryField(GeometryField):
    """Extended geometry field to properly handle export formats."""

    @cached_property
    def _output_format(self):
        # caching this object retrieval helps performance in CSV exports.
        # no need to resolve the root serializer all the time.
        request = self.context.get("request")
        if request is None:
            return None

        return request.accepted_renderer.format

    def to_internal_value(self, value):
        """Make sure that parsing remote data (e.g. proxy API) will set the correct CRS."""
        geom: GEOSGeometry = super().to_internal_value(value)

        # Assign the proper SRID value to the geometry, instead of the default EPSG:4326
        # The 'content_crs' is not parsed from the request, as it may come
        # from other sources such as a remote API that this serializer is parsing.
        if (content_crs := self.context.get("content_crs")) is not None:
            geom.srid = content_crs.srid

        return geom

    def to_representation(self, value):
        """Avoid GeoJSON export format for e.g. CSV exports"""
        if value is None:
            return None
        elif self._output_format == "csv":
            # Extended well-known text for CSV format.
            return value.ewkt
        else:
            # Return GeoJSON for json/html/api formats
            return super().to_representation(value)


class DSOURLField(serializers.URLField):
    """Ensure the URL is properly encoded"""

    def to_representation(self, value):
        try:
            bits = urlsplit(value)
        except ValueError:
            return value
        else:
            return urlunsplit(
                (bits.scheme, bits.netloc, quote(bits.path), quote(bits.query), bits.fragment)
            )


class GeoJSONIdentifierField(serializers.Field):
    """A field that renders the "id" field for a GeoJSON feature."""

    def __init__(self, model=None, **kwargs):
        kwargs["source"] = "*"
        kwargs["read_only"] = True
        super().__init__(**kwargs)
        self.model = model

    def bind(self, field_name, parent):
        super().bind(field_name, parent)
        if self.model is None:
            self.model = parent.Meta.model

    def to_representation(self, value):
        return f"{self.model._meta.object_name}.{value.pk}"
