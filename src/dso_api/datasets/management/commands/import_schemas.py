from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.db import create_tables
from dso_api.lib.schematools.utils import schema_defs_from_url


class Command(BaseCommand):
    help = "Import all known Amsterdam schema files."
    requires_system_checks = False

    def handle(self, *args, **options):  # noqa: C901
        errors = 0
        self.stdout.write(f"Loading schema from {settings.SCHEMA_URL}")
        datasets = []
        for name, schema in schema_defs_from_url(settings.SCHEMA_URL).items():

            if Dataset.objects.filter(name=schema.id).exists():
                self.stdout.write(f"* Skipping {name}, already imported")
                continue

            self.stdout.write(f"* Importing {name}")
            dataset = Dataset.objects.create(
                name=schema.id, schema_data=schema.json_data()
            )
            datasets.append(dataset)

        # Create the tables for all these datasets
        if not datasets:
            self.stdout.write(f"No new datasets imported")
        else:
            self.stdout.write(f"Creating tables")
            for dataset in datasets:
                try:
                    self.stdout.write(f"* Creating {dataset.name}")
                    with transaction.atomic():
                        create_tables(dataset.schema)
                except (DatabaseError, ValueError) as e:
                    self.stderr.write(f"  Tables not created: {e}")
                    errors += 1

        if errors:
            raise CommandError("Not all datasets imported successfully")
