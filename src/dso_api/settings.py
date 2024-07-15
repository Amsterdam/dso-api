import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

import environ
import sentry_sdk
import sentry_sdk.utils
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured
from opencensus.trace import config_integration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from dso_api.sentry import before_send

env = environ.Env()
_USE_SECRET_STORE = os.path.exists("/mnt/secrets-store")

# -- Environment

BASE_DIR = Path(__file__).parents[1]
DEBUG = env.bool("DJANGO_DEBUG", False)

CLOUD_ENV = env.str("CLOUD_ENV", "default").lower()
DJANGO_LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", "INFO")
DSO_API_LOG_LEVEL = env.str("DSO_API_LOG_LEVEL", "INFO")
DSO_API_AUDIT_LOG_LEVEL = env.str("DSO_API_AUDIT_LOG_LEVEL", "INFO")
SENTRY_BLOCKED_PATHS: Final[list[str]] = env.list("SENTRY_BLOCKED_PATHS", default=[])
ENABLE_REDIS = env.bool("ENABLE_REDIS", False)

STATIC_HOST = env.str("STATIC_HOST", "")
STATIC_URL = f"{STATIC_HOST}/v1/static/"
# Whitenoise needs a place to store static files and their gzipped versions.
STATIC_ROOT = env.str("DSO_STATIC_DIR")

# -- Datapunt settings
ENVIRONMENT_SUBDOMAIN = env.str("ENVIRONMENT_SUBDOMAIN", "data")

APIKEYSERV_API_URL = env.str(
    "APIKEYSERV_API_URL", f"https://keys.api.{ENVIRONMENT_SUBDOMAIN}.amsterdam.nl/"
)
DATAPUNT_API_URL = env.str("DATAPUNT_API_URL", "https://api.data.amsterdam.nl/")
SCHEMA_URL = env.str("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
PROFILES_URL = env.str("PROFILES_URL", "https://schemas.data.amsterdam.nl/profiles/")
SCHEMA_DEFS_URL = env.str("SCHEMA_DEFS_URL", "https://schemas.data.amsterdam.nl/schema")

# Authorization settings
OAUTH_URL = env.str(
    "OAUTH_URL", "https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/"
)
OAUTH_DEFAULT_SCOPE = env.str("OAUTH_DEFAULT_SCOPE", None)
OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "dso-api-open-api")

# -- Azure specific settings

# Microsoft recommended abbreviation for Application Insights is `APPI`
AZURE_APPI_CONNECTION_STRING: str | None = env.str("AZURE_APPI_CONNECTION_STRING", None)
AZURE_APPI_AUDIT_CONNECTION_STRING: str | None = env.str(
    "AZURE_APPI_AUDIT_CONNECTION_STRING", None
)

MAX_REPLICA_COUNT = env.int("MAX_REPLICA_COUNT", 5)

# -- Security

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY", "insecure")

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", not DEBUG)

INTERNAL_IPS = ("127.0.0.1",)

TIME_ZONE = "Europe/Amsterdam"

# -- Application definition

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
    "corsheaders",
    "drf_spectacular",
    "rest_framework",
    "rest_framework_gis",
    # Own apps
    "gisserver",
    "schematools.contrib.django",
    "dso_api",
    "dso_api.dynamic_api",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "authorization_django.authorization_middleware",
    "dso_api.middleware.AuthMiddleware",
]

if env.bool("APIKEY_ENABLED", True):
    MIDDLEWARE.append("apikeyclient.ApiKeyMiddleware")

AUTHENTICATION_BACKENDS = [
    "schematools.contrib.django.auth_backend.ProfileAuthorizationBackend",
]

if DEBUG:
    INSTALLED_APPS += [
        "debug_toolbar",
        "django_extensions",
    ]
    MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "dso_api.urls"

STATICFILES_DIRS = [str(BASE_DIR / "dso_api/static")]
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

if _USE_SECRET_STORE or CLOUD_ENV.startswith("azure"):
    # On Azure, passwords are NOT passed via environment variables,
    # because the container environment can be inspected, and those vars export to subprocesses.
    pgpassword = Path(env.str("AZ_PG_TOKEN_PATH")).read_text()

    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": env.str("PGDATABASE"),
            "USER": env.str("PGUSER"),
            "PASSWORD": pgpassword,
            "HOST": env.str("PGHOST"),
            "PORT": env.str("PGPORT"),
            "OPTIONS": {
                "sslmode": env.str("PGSSLMODE", default="require"),
            },
        }
    }
    DATABASE_SET_ROLE = True

    # Support up to 5 replicas configured with environment variables using
    # PGHOST_REPLICA_1 to PGHOST_REPLICA_5
    for replica_count in range(1, MAX_REPLICA_COUNT + 1):
        if env.str(f"PGHOST_REPLICA_{replica_count}", False):
            DATABASES.update(
                {
                    f"replica_{replica_count}": {
                        "ENGINE": "django.contrib.gis.db.backends.postgis",
                        "NAME": env.str("PGDATABASE"),
                        "USER": env.str("PGUSER"),
                        "PASSWORD": pgpassword,
                        "HOST": env.str(f"PGHOST_REPLICA_{replica_count}"),
                        "PORT": env.str("PGPORT"),
                        "OPTIONS": {
                            "sslmode": env.str("PGSSLMODE", default="require"),
                        },
                    }
                }
            )
        else:
            break

    if len(DATABASES) > 1:
        DATABASE_ROUTERS = ["dso_api.router.DatabaseRouter"]

    if ENABLE_REDIS:
        # Configure cache from a secret, so we cannot use CACHE_URL
        # because that would expose redis passwd in an env var.
        redis_password = Path(env.str("REDIS_PASSWD_PATH")).read_text()
        redis_host = env.str("REDIS_HOSTNAME")
        redis_port = env.int("REDIS_PORT", 6379)
        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                # "LOCATION": "redis://username:password@127.0.0.1:6379",
                # We leave out the username, defaults to `default` for redis
                "LOCATION": f"redis://:{redis_password}@{redis_host}:{redis_port}",
            }
        }
    else:
        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }

else:
    # Regular development
    DATABASES = {
        "default": env.db_url(
            "DATABASE_URL",
            default="postgres://dataservices:insecure@localhost:5415/dataservices",
            engine="django.contrib.gis.db.backends.postgis",
        ),
    }
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASE_SET_ROLE = env.bool("DATABASE_SET_ROLE", False)

DATABASES["default"]["OPTIONS"]["application_name"] = "DSO-API"

# These constants that are used for end-user context switching
# are configured in our dp-infra repo
USER_ROLE = "{user_email}_role"
INTERNAL_ROLE = "medewerker_role"
ANONYMOUS_ROLE = "anonymous_role"
ANONYMOUS_APP_NAME = "DSO-openbaar"

locals().update(env.email_url(default="smtp://"))

SENTRY_DSN = env.str("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="dso-api",
        before_send=before_send,
        integrations=[
            LoggingIntegration(event_level=logging.WARNING),
            DjangoIntegration(),
        ],
    )
    sentry_sdk.utils.MAX_STRING_LENGTH = 2048  # for WFS FILTER exceptions

base_log_fmt = {"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s"}
log_fmt = base_log_fmt.copy()
log_fmt["message"] = "%(message)s"

audit_log_fmt = {"audit": True}
audit_log_fmt.update(log_fmt)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "json": {"format": json.dumps(log_fmt)},
        "audit_json": {"format": json.dumps(audit_log_fmt)},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "audit_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "audit_json",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "opencensus": {"handlers": ["console"], "level": DJANGO_LOG_LEVEL, "propagate": False},
        "django": {"handlers": ["console"], "level": DJANGO_LOG_LEVEL, "propagate": False},
        "django.utils.autoreload": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "dso_api": {"handlers": ["console"], "level": DSO_API_LOG_LEVEL, "propagate": False},
        "dso_api.audit": {
            "handlers": ["audit_console"],
            "level": DSO_API_AUDIT_LOG_LEVEL,
            "propagate": False,
        },
        "rest_framework_dso": {
            "handlers": ["console"],
            "level": DSO_API_LOG_LEVEL,
            "propagate": False,
        },
        "authorization_django": {
            "handlers": ["audit_console"],
            "level": DSO_API_AUDIT_LOG_LEVEL,
            "propagate": False,
        },
        "apikeyclient": {"handlers": ["console"], "propagate": False},
    },
}

if CLOUD_ENV.lower().startswith("azure"):
    if AZURE_APPI_CONNECTION_STRING is None:
        raise ImproperlyConfigured(
            "Please specify the 'AZURE_APPI_CONNECTION_STRING' environment variable."
        )
    if AZURE_APPI_AUDIT_CONNECTION_STRING is None:
        logging.warning(
            "Using AZURE_APPI_CONNECTION_STRING as AZURE_APPI_AUDIT_CONNECTION_STRING."
        )

    MIDDLEWARE.append("opencensus.ext.django.middleware.OpencensusMiddleware")
    OPENCENSUS = {
        "TRACE": {
            "SAMPLER": "opencensus.trace.samplers.ProbabilitySampler(rate=1)",
            "EXPORTER": f"""opencensus.ext.azure.trace_exporter.AzureExporter(
                connection_string='{AZURE_APPI_CONNECTION_STRING}',
                service_name='dso-api'
            )""",  # noqa: E202
            "EXCLUDELIST_PATHS": [],
        }
    }
    config_integration.trace_integrations(["logging"])
    azure_json = base_log_fmt.copy()
    azure_json.update({"message": "%(message)s"})
    audit_azure_json = {"audit": True}
    audit_azure_json.update(azure_json)
    LOGGING["formatters"]["azure"] = {"format": json.dumps(azure_json)}
    LOGGING["formatters"]["audit_azure"] = {"format": json.dumps(audit_azure_json)}
    LOGGING["handlers"]["azure"] = {
        "level": "DEBUG",
        "class": "opencensus.ext.azure.log_exporter.AzureLogHandler",
        "connection_string": AZURE_APPI_CONNECTION_STRING,
        "formatter": "azure",
    }
    LOGGING["handlers"]["audit_azure"] = {
        "level": "DEBUG",
        "class": "opencensus.ext.azure.log_exporter.AzureLogHandler",
        "connection_string": AZURE_APPI_AUDIT_CONNECTION_STRING,
        "formatter": "audit_azure",
    }

    LOGGING["root"]["handlers"] = ["azure"]
    LOGGING["root"]["level"] = DJANGO_LOG_LEVEL
    for logger_name, logger_details in LOGGING["loggers"].items():
        if "audit_console" in logger_details["handlers"]:
            LOGGING["loggers"][logger_name]["handlers"] = ["audit_azure", "console"]
        else:
            LOGGING["loggers"][logger_name]["handlers"] = ["azure", "console"]

# -- Third party app settings

# Send Access-Control-Allow-Origin without Access-Control-Allow-Credentials
# for ArcGIS Online. HAProxy should handle the remaining cases by setting
#   Access-Control-Allow-Origin: $origin
#   Access-Control-Allow-Credentials: true
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://(?:\w+\.)*(?:arcgis.com)(?::\d+)?$"]

CORS_ALLOW_CREDENTIALS = False

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
    EXCEPTION_HANDLER="rest_framework_dso.views.exception_handler",
    COERCE_DECIMAL_TO_STRING=True,
    URL_FORMAT_OVERRIDE="_format",  # use ?_format=.. instead of ?format=..
    # View configuration
    VIEW_NAME_FUNCTION="rest_framework_dso.views.get_view_name",
)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

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
        "description": "API Usage Documentation",
        "url": "https://api.data.amsterdam.nl/v1/docs/",
    },
    "GET_MOCK_REQUEST": "dso_api.dynamic_api.openapi.build_mock_request",
    "SCHEMA_PATH_PREFIX": r"^/v?\d+(\.\d+)?/",  # strip /v1/ from tags.
    "SWAGGER_UI_SETTINGS": {
        "oauth2RedirectUrl": f"{DATAPUNT_API_URL}v1/oauth2-redirect.html",
        "clientId": OAUTH_CLIENT_ID,
        "scopes": OAUTH_DEFAULT_SCOPE,
    },
}

# -- Amsterdam oauth settings

DATAPUNT_AUTHZ = {
    # To verify JWT tokens, either the PUB_JWKS or a OAUTH_JWKS_URL needs to be set.
    "JWKS": os.getenv("PUB_JWKS"),
    "JWKS_URL": os.getenv("OAUTH_JWKS_URL"),
    # "ALWAYS_OK": True if DEBUG else False,
    "ALWAYS_OK": False,
    "MIN_INTERVAL_KEYSET_UPDATE": 30 * 60,  # 30 minutes
}

# -- Local app settings

AMSTERDAM_SCHEMA = {"geosearch_disabled_datasets": []}

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

# TODO the variables without _BAG_ are for BRK. Rename them.
if _USE_SECRET_STORE or CLOUD_ENV.startswith("azure"):
    HAAL_CENTRAAL_API_KEY = Path("/mnt/secrets-store/haalcentraal-api-key").read_text()
    HAAL_CENTRAAL_BAG_API_KEY = Path("/mnt/secrets-store/haalcentraal-bag-api-key").read_text()
else:
    HAAL_CENTRAAL_API_KEY = os.getenv("HAAL_CENTRAAL_API_KEY")
    HAAL_CENTRAAL_BAG_API_KEY = os.getenv("HAAL_CENTRAAL_BAG_API_KEY")

# Defaults to the acceptance endpoint. For production, set
# HAAL_CENTRAAL_BAG_ENDPOINT=https://api.bag.kadaster.nl/lvbag/individuelebevragingen/v2/
HAAL_CENTRAAL_BAG_ENDPOINT = os.getenv(
    "HAAL_CENTRAAL_BAG_ENDPOINT",
    "https://api.bag.acceptatie.kadaster.nl/lvbag/individuelebevragingen/v2/",
)

# Defaults to the acceptance endpoint. For production, set
# HAAL_CENTRAAL_BRK_ENDPOINT=https://api.brk.kadaster.nl/esd/bevragen/v1/
HAAL_CENTRAAL_BRK_ENDPOINT = os.getenv(
    "HAAL_CENTRAAL_BRK_ENDPOINT",
    "https://api.brk.acceptatie.kadaster.nl/esd/bevragen/v1/",
)

# mTLS client certificate for Haal Centraal BRK.
HAAL_CENTRAAL_KEYFILE = os.getenv("HC_KEYFILE")
HAAL_CENTRAAL_CERTFILE = os.getenv("HC_CERTFILE")

SHELL_PLUS_POST_IMPORTS = (
    "from django.apps.registry import apps",
    "from dso_api.dynamic_api.filterset import filterset_factory",
    "from dso_api.dynamic_api.serializers import serializer_factory",
    "from pprint import pprint",
)
APIKEY_MANDATORY = env.bool("APIKEY_MANDATORY", False)
APIKEY_ALLOW_EMPTY = env.bool("APIKEY_ALLOW_EMPTY", True)
APIKEY_ENDPOINT = env.str("APIKEY_ENDPOINT", "http://localhost:8001/signingkeys/")
APIKEY_LOCALKEYS = env.json("APIKEY_LOCALKEYS", None)
APIKEY_LOGGER = "opencensus"

# Initially we are proxy-ing from cvps HAProxy
USE_X_FORWARDED_HOST = True

SEAL_WARN_ONLY = True

# Configuration for canned exports
EXPORT_BASE_URI = env.str("BULK_ENDPOINT", "https://api.data.amsterdam.nl/bulk-data")

# Setting for django-gisserver, disabling this makes WFS much faster
GISSERVER_CAPABILITIES_BOUNDING_BOX = False
GISSERVER_COUNT_NUMBER_MATCHED = 0  # 0 = no counting, 1 = all pages, 2 = only first page
