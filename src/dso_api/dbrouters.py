from django.conf import settings
from django.db import connections


class DisableMigrationsRouter:
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Do not allow migration for 'bag'
        """
        if app_label in settings.DATABASE_DISABLE_MIGRATIONS:
            return False
        return None


class DatabaseSchemasRouter(DisableMigrationsRouter):
    """
    Database Router to allow use of PostgreSQL schemas.
    """

    def db_for_read(self, model, **hints):
        """
        Attempts to read bag go to bag_v11.
        """
        if model._meta.app_label in settings.DATABASE_SCHEMAS:
            schema_name = settings.DATABASE_SCHEMAS[model._meta.app_label]
            if schema_name not in connections.databases:
                new_connection = connections.databases["default"]
                new_connection["OPTIONS"] = {"options": f"-c search_path={schema_name},public"}
                connections.databases[schema_name] = new_connection
            return schema_name
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write.
        """
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        For now return None. Then relations are only allowed id they are in the same database.
        """
        return None
