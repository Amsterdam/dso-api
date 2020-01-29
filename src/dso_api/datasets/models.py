import logging
from typing import List, Type

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from dso_api.lib.schematools.models import DynamicModel, schema_models_factory
from dso_api.lib.schematools.types import DatasetSchema

logger = logging.getLogger(__name__)


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
        ordering = ("ordering", "name")
        verbose_name = _("Dataset")
        verbose_name_plural = _("Datasets")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Make sure the schema_data field is properly filled with an actual dict.
        if self.schema_data and not isinstance(self.schema_data, dict):
            logger.debug(
                "Invalid data in Dataset.schema_data, expected dict: %r",
                self.schema_data,
            )
            raise RuntimeError("Invalid data in Dataset.schema_data")

        super().save(*args, **kwargs)

    save.alters_data = True

    @cached_property
    def schema(self) -> DatasetSchema:
        """Provide access to the schema data"""
        if not self.schema_data:
            raise RuntimeError("Dataset.schema_data is empty")

        return DatasetSchema.from_dict(self.schema_data)

    def create_models(self) -> List[Type[DynamicModel]]:
        """Extract the models found in the schema"""
        return schema_models_factory(self.schema)
