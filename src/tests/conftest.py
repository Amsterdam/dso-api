import pytest
from django.conf import settings
from django.test.utils import override_settings
from rest_framework.test import APIRequestFactory


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    return APIRequestFactory()


def pytest_configure(config):
    """Override the """
    if settings.configured:
        # The reason the settings are defined here, is to make them independent
        # of the regular project sources. Otherwise, the project needs to have
        # knowledge of the test framework.
        override = override_settings(
            INSTALLED_APPS=settings.INSTALLED_APPS + [
                'tests.test_djangorestframework_dso',
            ],
            CSRF_COOKIE_SECURE=False,
            SESSION_COOKIE_SECURE=False,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        override.enable()
