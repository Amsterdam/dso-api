import os

import environ
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

env = environ.Env()

# -- Environment

BASE_DIR = str(environ.Path(__file__) - 2)
DEBUG = env.bool("DJANGO_DEBUG", True)

# Paths
STATIC_URL = "/v1/static/"
STATIC_ROOT = "/static/"

DATAPUNT_API_URL = env.str("DATAPUNT_API_URL", "https://api.data.amsterdam.nl/")
SCHEMA_URL = env.str("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")


# -- Security

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY", "insecure")

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", not DEBUG)

INTERNAL_IPS = ("127.0.0.1", "0.0.0.0")


# -- Application definition

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "corsheaders",
    "django_filters",
    "drf_yasg",
    "rest_framework",
    "rest_framework_gis",
    "gisserver",
    # Own apps
    "dso_api.datasets",
    "dso_api.dynamic_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if DEBUG:
    INSTALLED_APPS += [
        "debug_toolbar",
        "django_extensions",
    ]
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

ROOT_URLCONF = "dso_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "OPTIONS": {
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

if not DEBUG:
    # Keep templates in memory
    TEMPLATES[0]["OPTIONS"]["loaders"] = [
        ("django.template.loaders.cached.Loader", TEMPLATES[0]["OPTIONS"]["loaders"]),
    ]

WSGI_APPLICATION = "dso_api.wsgi.application"

# -- Services

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://dso_api:insecure@localhost:5415/dso_api",
        engine="django.contrib.gis.db.backends.postgis",
    ),
    "bag_v11": env.db_url(
        "BAG_V11_DATABASE_URL",
        default="postgres://bag_v11_read:insecure@localhost:5434/bag_v11",
        engine="django.contrib.gis.db.backends.postgis",
    ),
}

DATABASE_ROUTERS = ["dso_api.dbrouters.ExternDatabaseRouter"]

locals().update(env.email_url(default="smtp://"))

SENTRY_DSN = env.str("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env.str("SENTRY_ENVIRONMENT", default="dev")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()])


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        # 'django.db.backends': {
        #     'level': 'DEBUG',
        #     'handlers': ['console'],
        # },
        "dso_api": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

# -- Third party app settings

CORS_ORIGIN_ALLOW_ALL = True

HEALTH_CHECKS = {
    "app": lambda request: True,
    "database": "django_healthchecks.contrib.check_database",
    # 'cache': 'django_healthchecks.contrib.check_cache_default',
    # 'ip': 'django_healthchecks.contrib.check_remote_addr',
}
HEALTH_CHECKS_ERROR_CODE = 503

REST_FRAMEWORK = dict(
    PAGE_SIZE=20,
    MAX_PAGINATE_BY=20,
    UNAUTHENTICATED_USER={},
    UNAUTHENTICATED_TOKEN={},
    DEFAULT_AUTHENTICATION_CLASSES=[
        # 'rest_framework.authentication.BasicAuthentication',
        # 'rest_framework.authentication.SessionAuthentication',
    ],
    DEFAULT_PAGINATION_CLASS="rest_framework_dso.pagination.DSOPageNumberPagination",
    DEFAULT_RENDERER_CLASSES=[
        "rest_framework_dso.renderers.HALJSONRenderer",
        "dso_api.lib.renderers.PatchedBrowsableAPIRenderer",
    ],
    DEFAULT_FILTER_BACKENDS=[
        "django_filters.rest_framework.backends.DjangoFilterBackend",
    ],
    EXCEPTION_HANDLER="rest_framework_dso.views.exception_handler",
    COERCE_DECIMAL_TO_STRING=True,
)

SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": False,
    "SECURITY_DEFINITIONS": {
        "oauth2": {
            "type": "oauth2",
            "authorizationUrl": f"{DATAPUNT_API_URL}oauth2/authorize",
            "flow": "implicit",
        }
    },
}

# -- Local app settings

AMSTERDAM_SCHEMA = {"geosearch_disabled_datasets": ["bag"]}
