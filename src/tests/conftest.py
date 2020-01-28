import pytest
from rest_framework.test import APIRequestFactory


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()
