import pytest
from django.conf import settings
from django.db import connections
from dso_api.dbrouters import DatabaseSchemasRouter


@pytest.mark.django_db
class TestDatabaseSchemasRotuer:
    def test_db_for_read_returns_none_by_default(self, bagh_schema, bagh_models):
        db_router = DatabaseSchemasRouter()
        assert db_router.db_for_read(bagh_models["buurt"]) is None

    def test_db_for_read_returns_schema_name_if_set(self, bagh_schema, bagh_models):
        default_settings = settings.DATABASE_SCHEMAS.copy()
        settings.DATABASE_SCHEMAS["bagh"] = "test"
        db_router = DatabaseSchemasRouter()

        assert db_router.db_for_read(bagh_models["buurt"]) == "test"

        settings.DATABASE_SCHEMAS = default_settings

    def test_db_for_read_creates_new_connection_if_set(self, bagh_schema, bagh_models):
        default_settings = settings.DATABASE_SCHEMAS.copy()
        settings.DATABASE_SCHEMAS["bagh"] = "test"
        db_router = DatabaseSchemasRouter()

        db_router.db_for_read(bagh_models["buurt"])
        assert "test" in connections.databases
        assert (
            connections.databases["test"]["OPTIONS"]["options"]
            == "-c search_path=test,public"
        )

        settings.DATABASE_SCHEMAS = default_settings


@pytest.mark.django_db
class TestDisableMigrationsRouter:
    def test_allow_migrate_returns_none_by_default(self, bagh_schema, bagh_models):
        db_router = DatabaseSchemasRouter()
        assert db_router.allow_migrate(None, "bagh", "buurt") is None

    def test_allow_migrate_returns_false_if_set(self, bagh_schema, bagh_models):
        default_settings = settings.DATABASE_DISABLE_MIGRATIONS.copy()
        settings.DATABASE_DISABLE_MIGRATIONS = ["bagh"]
        db_router = DatabaseSchemasRouter()

        assert db_router.allow_migrate(None, "bagh", "buurt") is False

        settings.DATABASE_DISABLE_MIGRATIONS = default_settings
