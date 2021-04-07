"""Additional Django Form classes used internally by the extra filter fields."""

from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.forms import widgets
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError


class CharArrayField(forms.CharField):
    """Comma separated strings field"""

    default_error_messages = {
        "invalid_choice": _(
            "Select a valid choice. %(value)s is not one of the available choices."
        ),
        "invalid_list": _("Enter a list of values."),
    }

    def to_python(self, value):
        if not value:
            value = []
        elif isinstance(value, str):
            value = value.split(",")
        elif not isinstance(value, (list, tuple)):
            raise ValidationError(self.error_messages["invalid_list"], code="invalid_list")
        return [str(val) for val in value]


class MultipleValueWidget(widgets.Input):
    """Widget to retrieve all GET parameters instead of just a single value."""

    def value_from_datadict(self, data, files, name):
        try:
            return data.getlist(name)
        except AttributeError:
            # Unit testing with dict input
            value = data.get(name)
            return [value] if value is not None else None


class MultipleValueField(forms.Field):
    """Form field that returns all values."""

    default_error_messages = {"required": "Please specify one or more values."}
    widget = MultipleValueWidget

    def __init__(self, subfield: forms.Field, **kwargs):
        safe_kwargs = {
            k: kwargs.get(k, getattr(subfield, k, None))
            for k in (
                "required",
                "widget",
                "label",
                "initial",
                "help_text",
                "error_messages",
                "show_hidden_initial",
                "validators",
                "localize",
                "disabled",
                "label_suffix",
            )
        }
        super().__init__(**safe_kwargs)
        self.subfield = subfield

        # Enforce the "getlist" retrieval, even when a different widget was used.
        # The "__get__" is needed to retrieve the MethodType instead of the unbound function.
        if not isinstance(self.widget, MultipleValueWidget):
            self.widget.value_from_datadict = MultipleValueWidget.value_from_datadict.__get__(
                self.widget
            )

    def clean(self, values):
        if not values:
            if self.required:
                raise DjangoValidationError(self.error_messages["required"])
            else:
                return []

        if not isinstance(values, list):
            raise RuntimeError("MultipleValueField.widget does not return list of values")

        result = []
        errors = []
        for i, value in enumerate(values):
            try:
                result.append(self.subfield.clean(value))
            except DjangoValidationError as e:
                errors.append(e)

        if errors:
            raise DjangoValidationError(errors)

        return result
