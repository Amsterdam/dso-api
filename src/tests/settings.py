from dso_api.settings import *  # noqa: F403, F405

# The reason the settings are defined here, is to make them independent
# of the regular project sources. Otherwise, the project needs to have
# knowledge of the test framework.

INSTALLED_APPS += [
    "tests.test_rest_framework_dso",
]

TEST_NOINHERIT_ROLE = "user_application"
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://dataservices:insecure@localhost:5416/dataservices",
        engine="django.contrib.gis.db.backends.postgis",
    ),
}
TEST_USER_EMAIL = "test@tester.nl"
DB_USER = DATABASES["default"]["USER"]
DATABASE_SET_ROLE = False
OAUTH_URL = ""

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

# Prevent tests to crash because of missing staticfiles manifests
WHITENOISE_MANIFEST_STRICT = False
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# During testing we want to see if there is unwanted deferred access
SEAL_WARN_ONLY = False
