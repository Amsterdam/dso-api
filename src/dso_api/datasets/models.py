from __future__ import annotations

import logging
from typing import List, Type

from django.contrib.postgres.fields import JSONField
from django.db import models, transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from dso_api.lib.schematools.models import (
    DynamicModel,
    get_db_table_name,
    is_possible_display_field,
    schema_models_factory,
)
from amsterdam_schema.types import DatasetSchema, DatasetTableSchema

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The check makes sure that deferred fields are not checked for changes,
        # nor that creating the model
        self._old_schema_data = (
            self.schema_data
            if "schema_data" in self.__dict__ and not self._state.adding
            else None
        )

    def save(self, *args, **kwargs):
        """Perform a final data validation check, and additional updates."""
        if "schema_data" in self.__dict__:
            # Make sure the schema_data field is properly filled with an actual dict.
            if self.schema_data and not isinstance(self.schema_data, dict):
                logger.debug(
                    "Invalid data in Dataset.schema_data, expected dict: %r",
                    self.schema_data,
                )
                raise RuntimeError("Invalid data in Dataset.schema_data")

        if self.schema_data_changed() and (self.schema_data or not self._state.adding):
            self.__dict__.pop("schema", None)  # clear cached property
            # The extra "and" above avoids the transaction savepoint for an empty dataset.
            # Ensure both changes are saved together
            with transaction.atomic():
                super().save(*args, **kwargs)
                self.save_schema_tables()
        else:
            super().save(*args, **kwargs)

    save.alters_data = True

    def save_schema_tables(self):
        """Expose the schema data to the DatasetTable.
        This allows other projects (e.g. geosearch) to process our dynamic tables.
        """
        if not self.schema_data:
            # no schema stored -> no tables
            if self._old_schema_data:
                self.tables.all().delete()
            return

        new_definitions = {t.id: t for t in self.schema.tables}
        new_names = set(new_definitions.keys())
        existing_models = {t.name: t for t in self.tables.all()}
        existing_names = set(existing_models.keys())

        # Create models for newly added tables
        for added_name in new_names - existing_names:
            table = new_definitions[added_name]
            DatasetTable.create_for_schema(self, table)

        # Remove tables that are no longer part of the schema.
        for removed_name in existing_names - new_names:
            existing_models[removed_name].delete()

    save_schema_tables.alters_data = True

    @cached_property
    def schema(self) -> DatasetSchema:
        """Provide access to the schema data"""
        if not self.schema_data:
            raise RuntimeError("Dataset.schema_data is empty")

        return DatasetSchema.from_dict(self.schema_data)

    def schema_data_changed(self):
        """Check whether the schema_data attribute changed"""
        return (
            "schema_data" in self.__dict__  # this checks for deferred attributes
            and self.schema_data != self._old_schema_data
        )

    def create_models(self) -> List[Type[DynamicModel]]:
        """Extract the models found in the schema"""
        return schema_models_factory(self.schema)


class DatasetTable(models.Model):
    """Exposed metadata per schema.

    This table can be read by the 'geosearch' project to locate all our tables and data sources.
    """

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="tables"
    )
    name = models.CharField(max_length=100)

    # Exposed metadata from the jsonschema, so other utils can query these
    enable_geosearch = models.BooleanField(default=True)
    db_table = models.CharField(max_length=100, unique=True)
    display_field = models.CharField(max_length=50, null=True, blank=True)
    geometry_field = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Dataset Table")
        verbose_name_plural = _("Dataset Tables")
        unique_together = [
            ("dataset", "name"),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def create_for_schema(
        cls, dataset: Dataset, table: DatasetTableSchema
    ) -> DatasetTable:
        """Create a DatasetTable object based on the Amsterdam Schema table spec.

        (The table spec contains a JSON-schema for all fields).
        """
        display_field = None
        geometry_field = None
        for field in table.fields:
            # Take the first geojson field as geometry field
            if not geometry_field and field.type.startswith(
                "https://geojson.org/schema/"
            ):
                geometry_field = field.name
                break

            # Take the first string field as display name.
            if not display_field and is_possible_display_field(field):
                display_field = field.name

            if display_field and geometry_field:
                break

        return cls.objects.create(
            dataset=dataset,
            name=table.id,
            db_table=get_db_table_name(table),
            display_field=display_field,
            geometry_field=geometry_field,
        )
