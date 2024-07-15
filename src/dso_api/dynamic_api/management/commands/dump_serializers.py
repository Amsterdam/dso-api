import inspect
import textwrap
from argparse import ArgumentParser
from typing import Any, List, Optional, Tuple, Type

from django.apps import apps
from django.core.management import BaseCommand
from django.db import models
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from schematools.naming import to_snake_case
from schematools.permissions import UserScopes
from schematools.types import DatasetTableSchema

from dso_api.dynamic_api.serializers import DynamicSerializer
from dso_api.dynamic_api.urls import router
from rest_framework_dso.fields import AbstractEmbeddedField
from rest_framework_dso.renderers import HALJSONRenderer
from rest_framework_dso.serializers import DSOSerializer


class Command(BaseCommand):
    """Dump the dynamically generated models."""

    help = "Dump the (dynamic) serializer definitions that Django holds in-memory."  # noqa: A003

    path_aliases: List[Tuple[str, str]] = [
        ("rest_framework.fields.", "serializers."),
        ("rest_framework.relations.", "serializers."),
        ("dso_api.dynamic_api.serializers.", ""),
    ]

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Hook to add arguments."""
        parser.add_argument(
            "args", metavar="app_label", nargs="*", help="Names of Django apps to dump"
        )
        parser.add_argument(
            "--format",
            choices=["python", "nested"],
            default="python",
            help=(
                "Define the output format. Default is parsable Python,"
                " but nested Django REST Framework representation is also possible."
            ),
        )

    def handle(self, *args: str, **options: Any) -> None:
        """Main function of this command."""
        app_labels = set(args)
        current_app = None

        request = self._create_dummy_request()
        self.seen_serializers = set()  # state to avoid duplicate writes for embedded types

        for _prefix, viewset, _basename in sorted(router.registry):
            try:
                app_label = viewset.model._meta.app_label
            except AttributeError:
                # Remote serializer, no models in app registry.
                app_label = to_snake_case(viewset.table_schema.dataset.id)

            if app_labels and app_label not in app_labels:
                continue

            # Write a header each time a new app is dumped
            if app_label != current_app:
                self.write_header(app_label)
                current_app = app_label

            serializer = viewset.serializer_class(context={"request": request})
            self.dump_serializer(serializer, options["format"])

    def dump_serializer(self, serializer: DynamicSerializer, format: str):
        """Output the contents of a single serializer and it's child objects."""
        self.write_serializer_header(serializer)

        if format == "nested":
            # DRF has a nice __repr__ format for serializers and fields
            # that shows an inline nesting too.
            self.stdout.write(f"{serializer!r}\n\n\n")
        else:
            # Write the serializer as Python code that can be formatted.
            self.write_sub_serializers(serializer)
            self.write_serializer(serializer)

    def _create_dummy_request(self, path="/") -> Request:
        wsgi_request = APIRequestFactory().get(path)

        # Give access to all fields, so these can all be dumped.
        wsgi_request.user_scopes = UserScopes(query_params={}, request_scopes=[])
        wsgi_request.user_scopes.has_any_scope = lambda scopes: True
        wsgi_request.user_scopes.has_all_scopes = lambda scopes: True

        # Wrap in DRF request object, like the view would have done.
        drf_request = Request(wsgi_request)
        drf_request.accepted_renderer = HALJSONRenderer()

        # Add what DSOViewMixin would have added
        drf_request.accept_crs = None
        drf_request.response_content_crs = None
        return drf_request

    def write_header(self, app_label: str) -> None:
        """Write app start header."""
        try:
            app = apps.get_app_config(app_label)
        except LookupError:
            # Remote serializer, no models in app registry.
            self.stdout.write(f"# ---- App: {app_label}\n\n\n")
        else:
            self.stdout.write(f"# ---- App: {app.verbose_name or app.label}\n\n\n")

    def write_serializer_header(self, serializer: serializers.Serializer):
        """Write a header for the serializer, as it may have multiple child objects"""
        if isinstance(serializer, serializers.ModelSerializer):
            model = serializer.Meta.model
            app = apps.get_app_config(model._meta.app_label)
            self.stdout.write(
                f"# {app.verbose_name or app.app_label}.{model._meta.verbose_name}\n\n\n"
            )
        else:
            # Remote serializer:
            self.stdout.write(f"# {serializer.table_schema.qualified_id}\n\n\n")

    def write_sub_serializers(self, serializer: DSOSerializer):
        """Write the dependant serializers"""
        for _name, field in serializer.fields.items():
            if isinstance(field, serializers.Serializer):
                # Make sure generic serializers are not reprinted each time
                if field.__class__ in self.seen_serializers:
                    continue

                self.seen_serializers.add(field.__class__)

                # First write any sub-dependant fields (e.g. _links section items)
                self.write_sub_serializers(field)

                # Then write the serializer as any other regular serializer
                self.write_serializer(field)

    def write_serializer(self, serializer: DSOSerializer):
        """Write the representation of the serializer"""
        serializer_class = serializer.__class__
        bases = ", ".join(base_class.__name__ for base_class in serializer_class.__bases__)
        self.stdout.write(f"class {serializer_class.__name__}({bases}):\n")

        if serializer_class.__doc__:
            self.write_docstring(serializer_class.__doc__)

        self.write_factory_docs(serializer_class)

        # Split fields in auto created vs declared fields
        fields = dict(serializer.fields)
        declared_names = sorted(serializer._declared_fields.keys())
        for name in declared_names:
            field = fields.pop(name, None)
            if field is not None:  # e.g. "schema" field overwritten by subclass.
                self.write_field(field)

        if fields:
            self.stdout.write("\n    # Auto created fields during each request:\n")
            for field in fields.values():
                self.write_field(field)

        if hasattr(serializer_class, "Meta"):
            self.stdout.write("\n")
            self.write_serializer_meta(serializer_class)

        self.stdout.write("\n\n")

    def write_docstring(self, doc: str) -> None:
        """Write the docstring for a class."""
        if "\n" not in doc:  # if not formatted already
            # Wrap our description text
            doc = textwrap.fill(doc, 96, subsequent_indent="    ")
            if "\n" in doc:  # if wrapped
                doc += "\n"
        self.stdout.write(f'    """{doc}"""\n\n')

    def write_factory_docs(self, serializer_class: Type[DynamicSerializer]) -> None:
        """Write debugging information about the factory function."""
        # Write some factory information
        factory_name = self._get_serializer_factory_name(serializer_class)
        if issubclass(serializer_class, DynamicSerializer):
            self.stdout.write(f"    # Set by {factory_name}():\n")
            self.stdout.write(f"    # table_schema = {serializer_class.table_schema}\n")
            self.stdout.write("\n")
        else:
            self.stdout.write(f"    # Created by {factory_name}():\n")

    def write_serializer_meta(self, serializer_class: Type[DSOSerializer]) -> None:
        """Write the 'class Meta' section."""
        self.stdout.write("    class Meta:\n")
        for name, value in serializer_class.Meta.__dict__.items():
            if name.startswith("_"):
                continue

            if name == "embedded_fields":
                # Create a  __repr__ that is printable as actual Python.
                value = {
                    name: LiteralRepr(self._get_embedded_field_repr(field))
                    for name, field in value.items()
                }
            elif isinstance(value, type):
                value = LiteralRepr(value.__name__)

            self.stdout.write(f"        {name} = {value!r}\n")

    def write_field(self, field: serializers.Field) -> None:
        """Write how a field would have been written in a models file."""
        # Note that migration files use the 'name' from field.deconstruct()
        # but this is always identical to 'field.name' for standard Django fields.
        self.stdout.write(f"    {field.field_name} = {self._get_field_repr(field)}\n")

    def _get_embedded_field_repr(self, embedded_field: AbstractEmbeddedField):
        """Write a representation of the field as Python source code"""
        return (
            f"{embedded_field.__class__.__name__}"
            f"({embedded_field.serializer_class.__name__},"
            f" source='{embedded_field.source}'"
            ")"
        )

    def _get_field_repr(self, field: serializers.Field) -> str:
        """A Python-styled field representation (in contrast to the DRF one)"""
        if isinstance(field, serializers.Serializer):
            # Assume it's a direct generated class.
            path = field.__class__.__qualname__
        else:
            # Be somewhat intelligent to generate things like "serializers.IntegerField(..)"
            path = f"{field.__class__.__module__}.{field.__class__.__qualname__}"
            for prefix, alias in self.path_aliases:
                if path.startswith(prefix):
                    path = alias + path[len(prefix) :]

        comment = ""
        if isinstance(field, serializers.ListSerializer):
            comment = "  # Using many=True produces this list wrapper."

        # Note the IntegerField min_value / max_value originates from the model field;
        # which calls connection.ops.integer_field_range(field_type) to get these values.
        str_args = ", ".join(self._format_value(arg) for arg in field._args)
        str_kwargs = ", ".join(
            f"{n}={self._format_value(v)}" for n, v in sorted(field._kwargs.items())
        )
        return f"{path}({str_args}{str_kwargs}){comment}"

    def _format_value(self, value: Any) -> str:
        """Format the model kwarg, some callables should be mapped to their code name."""
        if isinstance(value, serializers.Field):
            # e.g. child_relation / child
            return self._get_field_repr(value)
        elif isinstance(value, type):
            # Class pointer
            return value.__name__
        elif isinstance(value, list):
            # for validators=[...]
            return "[{}]".format(",".join(self._format_value(v) for v in value))
        elif inspect.isfunction(value):
            # e.g. validators=[some_function]
            return f"{value.__module__}.{value.__qualname__}"
        elif getattr(value, "__module__", None) == "rest_framework.validators":
            # DRF Validator object has no common base class. Remove the <..>
            return repr(value).strip("<>")
        elif isinstance(value, DatasetTableSchema):
            # Generate some mock value that is valid Python
            return f"DATASETS['{value.dataset.id}']['{value.id}']"
        elif isinstance(value, models.Manager):
            return f"{value.model.__class__.__name__}.objects"

        return repr(value)

    def _get_serializer_factory_name(
        self, serializer_class: type[serializers.Serializer]
    ) -> Optional[str]:
        # Can be set by SerializerAssemblyLine.
        return getattr(serializer_class, "_factory_function", None)


class LiteralRepr:
    def __init__(self, repr_content):
        self.repr_content = repr_content

    def __repr__(self):
        return self.repr_content
