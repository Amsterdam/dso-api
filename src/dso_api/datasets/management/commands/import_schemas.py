from typing import List, Optional

from django.conf import settings
from django.core.management import BaseCommand

from dso_api.datasets.models import Dataset
from dso_api.lib.schematools.types import DatasetSchema
from dso_api.lib.schematools.utils import schema_defs_from_url

from .create_tables import create_tables


class Command(BaseCommand):
    help = "Import all known Amsterdam schema files."
    requires_system_checks = False

    def handle(self, *args, **options):
        datasets = self.import_schemas(settings.SCHEMA_URL)

        if not datasets:
            self.stdout.write(f"No new datasets imported")
        else:
            create_tables(self, datasets)

    def import_schemas(self, schema_url) -> List[Dataset]:
        """Import all schema definitions from an URL"""
        self.stdout.write(f"Loading schema from {schema_url}")
        datasets = []

        for name, schema in schema_defs_from_url(schema_url).items():
            self.stdout.write(f"* Processing {name}")
            dataset = self.import_schema(name, schema)
            if dataset is not None:
                datasets.append(dataset)

        return datasets

    def import_schema(self, name: str, schema: DatasetSchema) -> Optional[Dataset]:
        """Import a single dataset schema."""
        try:
            dataset = Dataset.objects.get(name=schema.id)
        except Dataset.DoesNotExist:
            dataset = Dataset.objects.create(
                name=schema.id, schema_data=schema.json_data()
            )
            self.stdout.write(f"  Created {name}")
            return dataset
        else:
            dataset.schema_data = schema.json_data()
            if dataset.schema_data_changed():
                dataset.save()
                self.stdout.write(f"  Updated {name}")
                return dataset

        return None
