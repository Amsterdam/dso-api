import json
import os

import pytest
from rest_framework.test import APIRequestFactory


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
