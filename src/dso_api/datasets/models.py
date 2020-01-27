from typing import List, Type

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from schematools.models import DynamicModel, schema_models_factory
from schematools.schema.types import DatasetSchema


class Dataset(models.Model):
    """A registry of all available datasets that are uploaded in the API server.

    Each model holds the contents of an "Amsterdam Schema",
    that contains multiple tables.
    """
    name = models.CharField(_("Name"), unique=True, max_length=50)
    ordering = models.IntegerField(_("Ordering"), default=1)
    enable_api = models.BooleanField(default=True)

    schema_data = JSONField(_("Amsterdam Schema Contents"))

    class Meta:
        ordering = ('ordering', 'name')
        verbose_name = _("Dataset")
        verbose_name_plural = _("Datasets")

    @cached_property
    def schema(self) -> DatasetSchema:
        """Provide access to the schema data"""
        return DatasetSchema.from_dict(self.schema_data)

    def create_models(self) -> List[Type[DynamicModel]]:
        """Extract the models found in the schema"""
        return schema_models_factory(self.schema)
