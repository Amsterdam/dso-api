from django.core.management import BaseCommand
from schematools.db import create_tables

from dso_api.datasets.models import Dataset


class Command(BaseCommand):
    help = "Create the tables based on the uploaded Amsterdam schema's."

    def handle(self, *args, **options):
        for dataset in Dataset.objects.all():
            self.stdout.write(f"* Creating {dataset}")
            create_tables(dataset.schema)
