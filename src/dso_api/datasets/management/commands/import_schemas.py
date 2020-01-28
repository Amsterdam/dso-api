from django.conf import settings
from django.core.management import BaseCommand
from django.db import transaction, DatabaseError
from schematools.db import create_tables
from schematools.schema.utils import schema_defs_from_url

from dso_api.datasets.models import Dataset


class Command(BaseCommand):
    help = "Import all known Amsterdam schema files."

    def handle(self, *args, **options):
        for name, schema in schema_defs_from_url(settings.SCHEMA_URL).items():

            if Dataset.objects.filter(name=schema.id).exists():
                self.stdout.write(f"* Skipping {name}, already imported")
                continue

            self.stdout.write(f"* Importing {name}")
            Dataset.objects.create(
                name=schema.id,
                schema_data=schema.json_data()
            )

            try:
                with transaction.atomic():
                    create_tables(schema)
            except DatabaseError as e:
                self.stderr.write(f"  Tables not created: {e}")
