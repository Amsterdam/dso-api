import re
from typing import Iterable

from django.core.management import BaseCommand, CommandError
from django.db import DatabaseError, connection, router, transaction

from dso_api.datasets.models import Dataset
from dso_api.lib.schematools.models import schema_models_factory


class Command(BaseCommand):
    help = "Create the tables based on the uploaded Amsterdam schema's."
    requires_system_checks = False  # don't test URLs (which create models)

    def handle(self, *args, **options):
        create_tables(self, Dataset.objects.all(), allow_unmanaged=True)


def create_tables(  # noqa:C901
    command: BaseCommand, datasets: Iterable[Dataset], allow_unmanaged=False
):  # noqa:C901
    """Create tables for all updated datasets.
    This is a separate function to allow easy reuse.
    """
    errors = 0
    command.stdout.write(f"Creating tables")

    # First create all models. This allows Django to resolve  model relations.
    models = []
    for dataset in datasets:
        models.extend(schema_models_factory(dataset.schema))

    # Create all tables
    with connection.schema_editor() as schema_editor:
        for model in models:
            # Only create tables if migration is allowed
            # - router allows it (not some external database)
            # - model is managed (not by default)
            # - user overrides this (e.g. developer)
            db_table_name = model._meta.db_table
            router_allows = router.allow_migrate_model(model._meta.app_label, model)
            if not router_allows:
                command.stdout.write(
                    f"  Skipping externally managed table: {db_table_name}"
                )
                continue

            if not allow_unmanaged and not model._meta.can_migrate(connection):
                command.stderr.write(
                    f"  Skipping non-managed model: {model._meta.db_table}"
                )
                continue

            try:
                command.stdout.write(f"* Creating table {model._meta.db_table}")
                with transaction.atomic():
                    schema_editor.create_model(model)
            except (DatabaseError, ValueError) as e:
                command.stderr.write(f"  Tables not created: {e}")
                if not re.search(r'relation "[^"]+" already exists', str(e)):
                    errors += 1

    if errors:
        raise CommandError("Not all tables could be created")
