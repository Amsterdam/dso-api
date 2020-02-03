import json
from pathlib import Path

import pytest
from django.db import connection
from rest_framework.test import APIClient, APIRequestFactory

from dso_api.datasets.models import Dataset
from dso_api.lib.schematools.db import create_tables
from dso_api.lib.schematools.types import DatasetSchema
from tests.test_rest_framework_dso.models import Category, Movie

HERE = Path(__file__).parent


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()


@pytest.fixture()
def api_client() -> APIClient:
    """Return a client that has unhindered access to the API views"""
    return APIClient()


@pytest.fixture()
def router():
    """Provide the router import as fixture.

    It can't be imported directly as urls.py accesses the database.
    The fixture also restores the application URL patterns after the test completed.
    """
    from dso_api.dynamic_api.urls import router

    assert (
        not router.registry
    ), "DynamicRouter already has URL patterns before test starts!"

    yield router

    # Only any changes that tests may have done to the router
    if router.registry:
        router.clear_urls()


@pytest.fixture()
def filled_router(router, afval_dataset, bommen_dataset):
    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 0

    # Make sure the tables are created too
    table_names = connection.introspection.table_names()
    if "afval_containers" not in table_names:
        create_tables(afval_dataset.schema)
    if "bommen_bommen" not in table_names:
        create_tables(bommen_dataset.schema)

    return router


@pytest.fixture()
def afval_schema_json() -> dict:
    path = HERE / "files/afval.json"
    return json.loads(path.read_text())


@pytest.fixture()
def afval_schema(afval_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(afval_schema_json)


@pytest.fixture()
def afval_dataset(afval_schema_json) -> Dataset:
    return Dataset.objects.create(name="afval", schema_data=afval_schema_json)


@pytest.fixture()
def bommen_schema_json() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/bommen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bommen_schema(bommen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(bommen_schema_json)


@pytest.fixture()
def bommen_dataset(bommen_schema_json) -> Dataset:
    return Dataset.objects.create(name="bommen", schema_data=bommen_schema_json)


@pytest.fixture
def category() -> Category:
    """A dummy model to test our API with"""
    return Category.objects.create(name="bar")


@pytest.fixture
def movie(category) -> Movie:
    """A dummy model to test our API with"""
    return Movie.objects.create(name="foo123", category=category)
