"""Additional filter classes to implement DSO filters."""
from datetime import datetime

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django_filters import fields
from django_filters.rest_framework import filters


class ModelIdChoiceField(fields.ModelChoiceField):
    """Allow testing an IN query against invalid ID's"""

    def to_python(self, value):
        """Bypass the queryset value check entirely.
        Copied the parts of the base method that are relevent here.
        """
        if self.null_label is not None and value == self.null_value:
            return value
        if value in self.empty_values:
            return None

        if isinstance(value, self.queryset.model):
            value = getattr(value, self.to_field_name or "pk")

        return value


class FlexDateTimeField(fields.IsoDateTimeField):
    """Allow input both as date or full datetime"""

    default_error_messages = {
        "invalid": _("Enter a valid ISO date-time, or single date."),
    }

    @cached_property
    def input_formats(self):
        # Note these types are lazy, hence the casts
        return list(fields.IsoDateTimeField.input_formats) + list(
            filters.DateFilter.field_class.input_formats
        )

    def strptime(self, value, format):
        if format in set(filters.DateFilter.field_class.input_formats):
            # Emulate forms.DateField.strptime()
            return datetime.strptime(value, format).date()
        else:
            return super().strptime(value, format)
