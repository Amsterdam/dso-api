from dso_api.settings import *

# The reason the settings are defined here, is to make them independent
# of the regular project sources. Otherwise, the project needs to have
# knowledge of the test framework.

INSTALLED_APPS += [
    "tests.test_rest_framework_dso",
]

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://dataservices:insecure@localhost:5416/dataservices",
        engine="django.contrib.gis.db.backends.postgis",
    ),
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

AZURE_BLOB_NGDSODEV = "test"

# Make sure the router is empty on start
INITIALIZE_DYNAMIC_VIEWSETS = False
