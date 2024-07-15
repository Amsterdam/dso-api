from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection
from psycopg2 import sql
from schematools.contrib.django.models import DynamicModel


class Command(BaseCommand):
    """Apply check constraint to models"""

    def handle(self, *args, **kwargs):
        """Main function of this command."""
        for app in apps.all_models:
            for model_name in apps.all_models[app]:
                model = apps.all_models[app][model_name]

                if not issubclass(model, DynamicModel):
                    continue

                schema = model.table_schema()
                pk = schema.identifier_fields[0]

                if len(schema.identifier) == 1 and pk.type == "string":
                    if model.objects.filter(**{f"{pk.python_name}__contains": "/"}).exists():
                        self.stdout.write(
                            self.style.WARNING(
                                f"Data in {schema.db_name} does not satisfy constraint.\
                                    Skipping this model...\n"
                            )
                        )
                        continue

                    with connection.cursor() as curs:
                        curs.execute(
                            sql.SQL(
                                "ALTER TABLE {table} DROP CONSTRAINT IF EXISTS id_not_contains_slash;"  # noqa: E501
                            ).format(table=sql.Identifier(schema.db_name))
                        )
                        curs.execute(
                            sql.SQL(
                                "ALTER TABLE {table} ADD CONSTRAINT id_not_contains_slash CHECK (NOT {field} LIKE '%%/%%');"  # noqa: E501
                            ).format(
                                table=sql.Identifier(schema.db_name),
                                field=sql.Identifier(pk.db_name),
                            )
                        )

                    self.stdout.write(
                        self.style.SUCCESS(f"Applied constraint on {schema.db_name}")
                    )
