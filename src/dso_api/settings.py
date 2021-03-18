import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import environ
import sentry_sdk
import sentry_sdk.utils
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured
from opencensus.trace import config_integration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


class CloudEnv(Enum):
    CLOUDVPS_DOCKER = "cloudvps_docker"
    AZURE_ACI = "azure_aci"
    AZURE_AKS = "azure_aks"

    def is_azure(self):
        return self in (CloudEnv.AZURE_ACI, CloudEnv.AZURE_AKS)


env = environ.Env()

# -- Environment

BASE_DIR = Path(__file__).parents[1]
DEBUG = env.bool("DJANGO_DEBUG", True)

CLOUD_ENV = CloudEnv(env.str("CLOUD_ENV", "cloudvps_docker"))
DJANGO_LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", "INFO")

# Paths
STATIC_URL = "/v1/static/"
STATIC_ROOT = "/static/"

DATAPUNT_API_URL = env.str("DATAPUNT_API_URL", "https://api.data.amsterdam.nl/")
SCHEMA_URL = env.str("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
PROFILES_URL = env.str("PROFILES_URL", "https://schemas.data.amsterdam.nl/profiles/")
SCHEMA_DEFS_URL = env.str("SCHEMA_DEFS_URL", "https://schemas.data.amsterdam.nl/schema")

# -- Azure specific settings

AZURE_INSTRUMENTATION_KEY: Optional[str] = env.str("AZURE_INSTRUMENTATION_KEY", None)
AZURE_INGESTION_ENDPOINT: Optional[str] = env.str("AZURE_INGESTION_ENDPOINT", None)
# -- Security

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY", "insecure")

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", not DEBUG)

INTERNAL_IPS = ("127.0.0.1", "0.0.0.0")

TIME_ZONE = "Europe/Amsterdam"

# -- Application definition

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "rest_framework",
    "rest_framework_gis",
    "gisserver",
    "schematools.contrib.django",
    # Own apps
    "dso_api.dynamic_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "authorization_django.authorization_middleware",
    "dso_api.dynamic_api.middleware.DatasetMiddleware",
    "dso_api.dynamic_api.middleware.TemporalDatasetMiddleware",
    "dso_api.dynamic_api.middleware.RequestAuditLoggingMiddleware",
]
connection_string: Optional[str] = None
if CLOUD_ENV.is_azure():
    if AZURE_INSTRUMENTATION_KEY is None:
        raise ImproperlyConfigured(
            "Please specify the 'AZURE_INSTRUMENTATION_KEY' environment variable."
        )
    if AZURE_INGESTION_ENDPOINT is None:
        raise ImproperlyConfigured(
            "Please specify the 'AZURE_INGESTION_ENDPOINT' environment variable."
        )
    MIDDLEWARE.append("opencensus.ext.django.middleware.OpencensusMiddleware")
    connection_string = (
        f"InstrumentationKey={AZURE_INSTRUMENTATION_KEY}"
        f";IngestionEndpoint={AZURE_INGESTION_ENDPOINT}"
    )
    OPENCENSUS = {
        "TRACE": {
            "SAMPLER": "opencensus.trace.samplers.ProbabilitySampler(rate=1)",
            "EXPORTER": f"""opencensus.ext.azure.trace_exporter.AzureExporter(
                connection_string='{connection_string}',
                service_name='dso-api'
            )""",
            "EXCLUDELIST_PATHS": [],
        }
    }

AUTHENTICATION_BACKENDS = [
    "schematools.contrib.django.auth_backend.ProfileAuthorizationBackend",
    "django.contrib.auth.backends.ModelBackend",
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
        "DIRS": [str(BASE_DIR / "templates")],
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

CACHES = {"default": env.cache_url(default="locmemcache://")}

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://dataservices:insecure@localhost:5415/dataservices",
        engine="django.contrib.gis.db.backends.postgis",
    ),
    "bag_v11_read": env.db_url(
        "BAG_V11_DATABASE_URL",
        default="postgres://bag_v11:insecure@localhost:5434/bag_v11",
        engine="django.contrib.gis.db.backends.postgis",
    ),
}
# Important to have keys define in DATABASE_SCHEMAS available as in DATABASES.
DATABASE_SCHEMAS = {}
DATABASE_DISABLE_MIGRATIONS = []

DATABASE_ROUTERS = ["dso_api.dbrouters.DatabaseSchemasRouter"]

locals().update(env.email_url(default="smtp://"))

SENTRY_DSN = env.str("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="dso-api",
        integrations=[
            LoggingIntegration(event_level=logging.WARNING),
            DjangoIntegration(),
        ],
    )
    sentry_sdk.utils.MAX_STRING_LENGTH = 2048  # for WFS FILTER exceptions

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "console": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"},
        "structured_console": {
            "format": (
                '{"time": "%(asctime)s", '
                '"name": "%(name)s", '
                '"level": "%(levelname)s", '
                '"message": %(message)s}'
            )
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
        "structured_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "structured_console",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "django": {"handlers": ["console"], "level": DJANGO_LOG_LEVEL, "propagate": False},
        "dso_api": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "dso_api.audit": {
            "handlers": ["structured_console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
if CLOUD_ENV.is_azure():
    assert connection_string is not None, "`connection_string` should have been configured by now."
    config_integration.trace_integrations(["logging"])
    LOGGING["formatters"]["azure"] = {
        "format": (
            '{"time": "%(asctime)s", '
            '"name": "%(name)s", '
            '"level": "%(levelname)s", '
            '"trace_id": "%(traceId)s", '
            '"span_id": "%(spanId)s" '
            '"message": %(message)s}'
        )
    }
    LOGGING["handlers"]["azure"] = {
        "level": "DEBUG",
        "class": "opencensus.ext.azure.log_exporter.AzureLogHandler",
        "connection_string": connection_string,
        "formatter": "azure",
    }
    LOGGING["root"]["handlers"] = ["azure"]
    for logger in LOGGING["loggers"]:
        LOGGING["loggers"][logger]["handlers"] = ["azure"]

# -- Third party app settings

# Do not set CORS_ALLOW_ALL_ORIGINS to True
# The Access-Control-Allow-Origin should  ot de set to *
# That will conflict with the  Access-Control-Allow-Credentials: true
# set by HAProxy. If Access-Control-Allow-Origin is not set here it will
# be set correctly  to the Origin by HAProxy

CORS_ALLOW_HEADERS = list(default_headers) + [
    "Accept-Crs",
    "Content-Crs",
]

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
    DEFAULT_SCHEMA_CLASS="rest_framework_dso.openapi.DSOAutoSchema",
    DEFAULT_RENDERER_CLASSES=[
        "rest_framework_dso.renderers.HALJSONRenderer",
        "rest_framework_dso.renderers.CSVRenderer",
        "rest_framework_dso.renderers.GeoJSONRenderer",
        "rest_framework_dso.renderers.BrowsableAPIRenderer",
    ],
    DEFAULT_FILTER_BACKENDS=[
        "django_filters.rest_framework.backends.DjangoFilterBackend",
    ],
    EXCEPTION_HANDLER="rest_framework_dso.views.exception_handler",
    COERCE_DECIMAL_TO_STRING=True,
    URL_FORMAT_OVERRIDE="_format",  # use ?_format=.. instead of ?format=..
)

SPECTACULAR_SETTINGS = {
    "TITLE": "DSO-API",
    "VERSION": "v1",
    "DESCRIPTION": (
        """
This is the generic [DSO-compatible](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/) API server.

The following features are supported:

* HAL-JSON based links, pagination and response structure.
* Use `?_expandScope=name1,name2` to sideload specific relations.
* Use `?_expand=true` to sideload all relations.

The models in this server are generated from the Amsterdam Schema files.
These are located at:
[https://schemas.data.amsterdam.nl/datasets/](https://schemas.data.amsterdam.nl/datasets/)
"""  # noqa: E501
    ),
    "TOS": "https://data.amsterdam.nl/",
    "CONTACT": {"email": "datapunt@amsterdam.nl"},
    "LICENSE": {"name": "CC0 1.0 Universal"},
    "EXTERNAL_DOCS": {
        "description": "API usage Documentation",
        "url": "https://api.data.amsterdam.nl/v1/docs/",
    },
    "SCHEMA_PATH_PREFIX": r"^/v?\d+(\.\d+)?/",  # strip /v1/ from tags.
}

# -- Amsterdam oauth settings

# The following JWKS data was obtained in the authz project :  jwkgen -create -alg ES256
# This is a test public/private key def and added for testing .
JWKS_TEST_KEY = """
    {
        "keys": [
            {
                "kty": "EC",
                "key_ops": [
                    "verify",
                    "sign"
                ],
                "kid": "2aedafba-8170-4064-b704-ce92b7c89cc6",
                "crv": "P-256",
                "x": "6r8PYwqfZbq_QzoMA4tzJJsYUIIXdeyPA27qTgEJCDw=",
                "y": "Cf2clfAfFuuCB06NMfIat9ultkMyrMQO9Hd2H7O9ZVE=",
                "d": "N1vu0UQUp0vLfaNeM0EDbl4quvvL6m_ltjoAXXzkI3U="
            }
        ]
    }
"""

DATAPUNT_AUTHZ = {
    "JWKS": os.getenv("PUB_JWKS", JWKS_TEST_KEY),
    "JWKS_URL": os.getenv("KEYCLOAK_JWKS_URL"),
    # "ALWAYS_OK": True if DEBUG else False,
    "ALWAYS_OK": False,
    "MIN_INTERVAL_KEYSET_UPDATE": 30 * 60,  # 30 minutes
}

# -- Local app settings

AMSTERDAM_SCHEMA = {"geosearch_disabled_datasets": ["bag", "meetbouten"]}

# On unapplied migrations, the Django 'check' fails when trying to
# Fetch datasets from the database. Viewsets are not needed when migrating.
INITIALIZE_DYNAMIC_VIEWSETS = env.bool(
    "INITIALIZE_DYNAMIC_VIEWSETS",
    default={"migrate", "makemigrations", "showmigrations"}.isdisjoint(sys.argv[1:]),
)

# WARNING: use with care, dangerous settings.
# Both DATASETS_LIST and DATASETS_EXCLUDE will limit list of datasets loaded into memory.
#  Relations to datasets outside list are not loaded automatically,
#  this means dso-api will break on pages where related datasets are missing.
# DATASETS_LIST: will load only provided datasets into memory.
# DATASETS_EXCLUDE: will load all datasets except provided in list.
DATASETS_LIST = env.list("DATASETS_LIST", default=None)
DATASETS_EXCLUDE = env.list("DATASETS_EXCLUDE", default=None)

# Dynamicaly import Azure Blob connections from environment
for key, value in env.ENVIRON.items():
    if key.startswith("AZURE_BLOB_"):
        locals()[key] = value

HAAL_CENTRAAL_API_KEY = os.getenv("HAAL_CENTRAAL_API_KEY", "UNKNOWN")
HAAL_CENTRAAL_KEYFILE = os.getenv("HC_KEYFILE")
HAAL_CENTRAAL_CERTFILE = os.getenv("HC_CERTFILE")
