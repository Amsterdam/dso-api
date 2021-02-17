"""Logic to implement object embedding, and retrieval in a streaming-like fashion.

It's written in an observer/listener style, allowing the embedded data to be determined
during the rendering. Instead of having to load the main results in memory for analysis,
the main objects are inspected while they are consumed by the output stream.
"""
from typing import Dict, Optional, Union

from rest_framework import serializers
from rest_framework.exceptions import ParseError, PermissionDenied

from dso_api.dynamic_api.permissions import fetch_scopes_for_model
from rest_framework_dso.fields import AbstractEmbeddedField, EmbeddedField
from rest_framework_dso.serializer_helpers import ReturnGenerator, peek_iterable

EmbeddedFieldDict = Dict[str, AbstractEmbeddedField]


def get_expanded_fields(  # noqa: C901
    parent_serializer: serializers.Serializer, fields_to_expand: Union[list, bool]
) -> Dict[str, EmbeddedField]:
    """Find the expanded fields in a serializer that are requested.
    This translates the ``_expand`` query into a dict of embedded fields.
    """
    if not fields_to_expand:
        return {}

    allowed_names = getattr(parent_serializer.Meta, "embedded_fields", [])
    auth_checker = getattr(parent_serializer, "get_auth_checker", lambda: None)()
    embedded_fields = {}

    # ?_expand=true should expand all names
    auto_expand_all = fields_to_expand is True
    if auto_expand_all:
        fields_to_expand = allowed_names

    for field_name in fields_to_expand:
        if field_name not in allowed_names:
            raise _expand_parse_error(allowed_names, field_name) from None

        # Get the field
        try:
            field = getattr(parent_serializer, field_name)
        except AttributeError:
            raise RuntimeError(
                f"{parent_serializer.__class__.__name__}.{field_name}"
                f" does not refer to an embedded field."
            ) from None

        # Check access via scopes (NOTE: this is higher-level functionality)
        scopes = fetch_scopes_for_model(field.related_model)
        if auth_checker and not auth_checker(*scopes.table):
            # Not allowed, silently drop for _expand=true request.
            if auto_expand_all:
                continue

            # Explicitly mentioned, raise error.
            raise PermissionDenied(f"Eager loading not allowed for field '{field_name}'")

        embedded_fields[field_name] = field

    return embedded_fields


def _expand_parse_error(allowed_names, field_name):
    """Generate the proper exception for the invalid expand name"""
    available = ", ".join(sorted(allowed_names))
    if not available:
        return ParseError("Eager loading is not supported for this endpoint")
    else:
        return ParseError(
            f"Eager loading is not supported for field '{field_name}', "
            f"available options are: {available}"
        )


class ObservableIterator:
    """Observe the objects that are being returned.

    Unlike itertools.tee(), retrieved objects are directly processed by other functions.
    As built-in feature, the number of returned objects is also counted.
    """

    def __init__(self, iterable, observers=None):
        self.number_returned = 0
        self._iterable = iter(iterable)
        self._item_callbacks = list(observers) if observers else []
        self._has_items = None

    def add_observer(self, callback):
        """Install an observer callback that is notified when items are iterated"""
        self._item_callbacks.append(callback)

    def __iter__(self):
        return self

    def __next__(self):
        """Keep a count of the returned items, and allow to notify other generators"""
        try:
            value = next(self._iterable)
        except StopIteration:
            self._is_iterated = True
            raise

        self.number_returned += 1
        self._has_items = True

        # Notify observers
        for notify_callback in self._item_callbacks:
            notify_callback(value)

        return value

    def __bool__(self):
        """Tell whether the generator would contain items."""
        if self._has_items is None:
            # Perform an inspection of the generator:
            first_item, items = peek_iterable(self._iterable)
            self._iterable = items
            self._has_items = first_item is not None

        return self._has_items


class EmbeddedResultSet(ReturnGenerator):
    """A wrapper for the returned expanded fields.
    This is used in combination with the ObservableIterator.

    The :func:`inspect_instance` is called each time an object is retrieved.
    As alternative, all instances *can* be provided at construction, which is
    typically useful for a detail page as this breaks streaming otherwise.
    """

    def __init__(
        self,
        embedded_field: EmbeddedField,
        serializer: serializers.Serializer,
        main_instances: Optional[list] = None,
        id_fetcher=None,
    ):
        super().__init__(generator=None, serializer=serializer)
        self.embedded_field = embedded_field
        self.id_list = []
        self.id_fetcher = id_fetcher

        if id_fetcher is None and serializer.parent.id_based_fetcher:
            # Fallback to serializer based ID-fetcher if needed.
            self.id_fetcher = serializer.parent.id_based_fetcher(
                model=embedded_field.related_model, is_loose=embedded_field.is_loose
            )

        # Allow to pre-feed with instances (e.g for detail view)
        if main_instances is not None:
            for instance in main_instances:
                self.inspect_instance(instance)

    def inspect_instance(self, instance):
        """Inspect a main object to find any references for this embedded result."""
        ids = self.embedded_field.get_related_ids(instance)
        if ids:
            self.id_list.extend(ids)

    def get_objects(self):
        """Retrieve the objects to render"""
        if self.id_fetcher is not None:
            # e.g. retrieve from a remote API, or filtered database table.
            return self.id_fetcher(self.id_list)
        else:
            # Standard Django foreign-key like behavior.
            model = self.embedded_field.related_model
            return model.objects.filter(pk__in=self.id_list).iterator()

    def __iter__(self):
        """Create the generator on demand when iteration starts.
        At this point, the ID's are known that need to be fetched.
        """
        if not self.id_list:
            return iter(())  # Avoid querying databases for empty sets.

        if self.generator is None:
            self.generator = self._build_generator()

        return super().__iter__()  # returns iter(self.generator)

    def __bool__(self):
        if self.generator is None:
            self.generator = self._build_generator()
        return super().__bool__()

    def _build_generator(self):
        """Create the generator on-demand"""
        return (self.serializer.to_representation(instance) for instance in self.get_objects())
