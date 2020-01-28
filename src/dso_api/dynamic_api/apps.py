import sys

from django.apps import AppConfig


class DynamicAPIApp(AppConfig):
    name = 'dso_api.dynamic_api'

    def ready(self):
        from django.db import connection
        from dso_api.datasets.models import Dataset
        from dso_api.dynamic_api.urls import router

        # Don't query the non-test database for the datasets
        if "pytest" in sys.modules:
            return

        # Only start the reload when the project already migrated the base tables:
        if Dataset._meta.db_table in connection.introspection.table_names():
            # Tell the router to reload, and initialize the missing URL patterns
            # now that we're ready to read the model data.
            router.initialize()
