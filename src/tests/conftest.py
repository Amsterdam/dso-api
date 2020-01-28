import json
import os

import pytest
from rest_framework.test import APIRequestFactory

from dso_api.datasets.models import Dataset


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()


@pytest.fixture()
def bommen_schema_json() -> dict:
    """Fixture to return the schema json for """
    filename = os.path.join(os.path.dirname(__file__), 'files/bommen.json')
    with open(filename) as fh:
        return json.loads(fh.read())


@pytest.fixture()
def bommen_dataset(bommen_schema_json) -> Dataset:
    return Dataset.objects.create(name="bommen", schema_data=bommen_schema_json)


@pytest.fixture()
def router():
    """Provide the router import as fixture.
    It can't be imported directly as it read the database.
    """
    from dso_api.dynamic_api.urls import router
    return router
