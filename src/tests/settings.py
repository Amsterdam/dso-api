from pathlib import Path

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

# Load public/private test key pair.
# This was obtained in the authz project with: jwkgen -create -alg ES256
jwks_key = Path(__file__).parent.parent.joinpath("jwks_test.json").read_text()

DATAPUNT_AUTHZ = {
    "JWKS": jwks_key,
    "ALWAYS_OK": False,
    "MIN_INTERVAL_KEYSET_UPDATE": 30 * 60,  # 30 minutes
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Make sure the router is empty on start
INITIALIZE_DYNAMIC_VIEWSETS = False
