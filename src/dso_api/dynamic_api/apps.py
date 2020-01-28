import sys

from django.apps import AppConfig


class DynamicAPIApp(AppConfig):
    name = 'dso_api.dynamic_api'

    def ready(self):
        from django.db import connection
        from dso_api.datasets.models import Dataset
        from dso_api.dynamic_api.urls import router

        # Don't query the non-test database for the datasets,
        # nor perform queries for management cool
        command = sys.argv[1] if len(sys.argv) >= 2 else ''
        if "pytest" in sys.modules or command in ('collectstatic', 'compilemessages'):
            return

        # Only start the reload when the project already migrated the base tables:
        if Dataset._meta.db_table in connection.introspection.table_names():
            # Tell the router to reload, and initialize the missing URL patterns
            # now that we're ready to read the model data.
            router.initialize()
