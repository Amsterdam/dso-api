import pytest
from django.conf import settings
from django.test.utils import override_settings
from pytest_django.plugin import _blocking_manager
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
                'tests.test_rest_framework_dso',
            ],
            CSRF_COOKIE_SECURE=False,
            SESSION_COOKIE_SECURE=False,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )

        # Normally, the django-db-blocker fixture needs to be used for this,
        # but in our case, the application needs to access DynamicAPIApp.ready()
        # need to access the database.
        with _blocking_manager.unblock():
            override.enable()
