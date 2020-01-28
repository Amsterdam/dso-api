from django.core.management import BaseCommand

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.db import create_tables


class Command(BaseCommand):
    help = "Create the tables based on the uploaded Amsterdam schema's."

    def handle(self, *args, **options):
        for dataset in Dataset.objects.all():
            self.stdout.write(f"* Creating {dataset}")
            create_tables(dataset.schema)
