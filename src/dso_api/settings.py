import logging
import os
import sys

import environ
import sentry_sdk
import sentry_sdk.utils
from corsheaders.defaults import default_headers
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

env = environ.Env()

# -- Environment

BASE_DIR = str(environ.Path(__file__) - 2)
DEBUG = env.bool("DJANGO_DEBUG", True)

# Paths
STATIC_URL = "/v1/static/"
STATIC_ROOT = "/static/"

DATAPUNT_API_URL = env.str("DATAPUNT_API_URL", "https://api.data.amsterdam.nl/")
SCHEMA_URL = env.str("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
PROFILES_URL = env.str("PROFILES_URL", "https://schemas.data.amsterdam.nl/profiles/")
SCHEMA_DEFS_URL = env.str("SCHEMA_DEFS_URL", "https://schemas.data.amsterdam.nl/schema")


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
    "django.contrib.sessions",
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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "authorization_django.authorization_middleware",
    "dso_api.dynamic_api.middleware.DatasetMiddleware",
    "dso_api.dynamic_api.middleware.TemporalDatasetMiddleware",
    "dso_api.dynamic_api.middleware.RequestAuditLoggingMiddleware",
]

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
    "disable_existing_loggers": False,
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
        # "django.db.backends": {"level": "DEBUG", "handlers": ["console"]},
        "dso_api": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "dso_api.audit": {
            "handlers": ["structured_console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

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
    "SWAGGER_UI_SETTINGS": {
        "oauth2RedirectUrl": "http://localhost:8000/v1/oauth2-redirect.html",
    }
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

# https://login.microsoftonline.com/72fca1b1-2c2e-4376-a445-294d80196804/discovery/keys
# JWKS_TEST_KEY = """{"keys":[{"kty":"RSA","use":"sig","kid":"nOo3ZDrODXEK1jKWhXslHR_KXEg","x5t":"nOo3ZDrODXEK1jKWhXslHR_KXEg","n":"oaLLT9hkcSj2tGfZsjbu7Xz1Krs0qEicXPmEsJKOBQHauZ_kRM1HdEkgOJbUznUspE6xOuOSXjlzErqBxXAu4SCvcvVOCYG2v9G3-uIrLF5dstD0sYHBo1VomtKxzF90Vslrkn6rNQgUGIWgvuQTxm1uRklYFPEcTIRw0LnYknzJ06GC9ljKR617wABVrZNkBuDgQKj37qcyxoaxIGdxEcmVFZXJyrxDgdXh9owRmZn6LIJlGjZ9m59emfuwnBnsIQG7DirJwe9SXrLXnexRQWqyzCdkYaOqkpKrsjuxUj2-MHX31FqsdpJJsOAvYXGOYBKJRjhGrGdONVrZdUdTBQ","e":"AQAB","x5c":["MIIDBTCCAe2gAwIBAgIQN33ROaIJ6bJBWDCxtmJEbjANBgkqhkiG9w0BAQsFADAtMSswKQYDVQQDEyJhY2NvdW50cy5hY2Nlc3Njb250cm9sLndpbmRvd3MubmV0MB4XDTIwMTIyMTIwNTAxN1oXDTI1MTIyMDIwNTAxN1owLTErMCkGA1UEAxMiYWNjb3VudHMuYWNjZXNzY29udHJvbC53aW5kb3dzLm5ldDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAKGiy0/YZHEo9rRn2bI27u189Sq7NKhInFz5hLCSjgUB2rmf5ETNR3RJIDiW1M51LKROsTrjkl45cxK6gcVwLuEgr3L1TgmBtr/Rt/riKyxeXbLQ9LGBwaNVaJrSscxfdFbJa5J+qzUIFBiFoL7kE8ZtbkZJWBTxHEyEcNC52JJ8ydOhgvZYykete8AAVa2TZAbg4ECo9+6nMsaGsSBncRHJlRWVycq8Q4HV4faMEZmZ+iyCZRo2fZufXpn7sJwZ7CEBuw4qycHvUl6y153sUUFqsswnZGGjqpKSq7I7sVI9vjB199RarHaSSbDgL2FxjmASiUY4RqxnTjVa2XVHUwUCAwEAAaMhMB8wHQYDVR0OBBYEFI5mN5ftHloEDVNoIa8sQs7kJAeTMA0GCSqGSIb3DQEBCwUAA4IBAQBnaGnojxNgnV4+TCPZ9br4ox1nRn9tzY8b5pwKTW2McJTe0yEvrHyaItK8KbmeKJOBvASf+QwHkp+F2BAXzRiTl4Z+gNFQULPzsQWpmKlz6fIWhc7ksgpTkMK6AaTbwWYTfmpKnQw/KJm/6rboLDWYyKFpQcStu67RZ+aRvQz68Ev2ga5JsXlcOJ3gP/lE5WC1S0rjfabzdMOGP8qZQhXk4wBOgtFBaisDnbjV5pcIrjRPlhoCxvKgC/290nZ9/DLBH3TbHk8xwHXeBAnAjyAqOZij92uksAv7ZLq4MODcnQshVINXwsYshG1pQqOLwMertNaY5WtrubMRku44Dw7R"]},{"kty":"RSA","use":"sig","kid":"l3sQ-50cCH4xBVZLHTGwnSR7680","x5t":"l3sQ-50cCH4xBVZLHTGwnSR7680","n":"sfsXMXWuO-dniLaIELa3Pyqz9Y_rWff_AVrCAnFSdPHa8__Pmkbt_yq-6Z3u1o4gjRpKWnrjxIh8zDn1Z1RS26nkKcNg5xfWxR2K8CPbSbY8gMrp_4pZn7tgrEmoLMkwfgYaVC-4MiFEo1P2gd9mCdgIICaNeYkG1bIPTnaqquTM5KfT971MpuOVOdM1ysiejdcNDvEb7v284PYZkw2imwqiBY3FR0sVG7jgKUotFvhd7TR5WsA20GS_6ZIkUUlLUbG_rXWGl0YjZLS_Uf4q8Hbo7u-7MaFn8B69F6YaFdDlXm_A0SpedVFWQFGzMsp43_6vEzjfrFDJVAYkwb6xUQ","e":"AQAB","x5c":["MIIDBTCCAe2gAwIBAgIQWPB1ofOpA7FFlOBk5iPaNTANBgkqhkiG9w0BAQsFADAtMSswKQYDVQQDEyJhY2NvdW50cy5hY2Nlc3Njb250cm9sLndpbmRvd3MubmV0MB4XDTIxMDIwNzE3MDAzOVoXDTI2MDIwNjE3MDAzOVowLTErMCkGA1UEAxMiYWNjb3VudHMuYWNjZXNzY29udHJvbC53aW5kb3dzLm5ldDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALH7FzF1rjvnZ4i2iBC2tz8qs/WP61n3/wFawgJxUnTx2vP/z5pG7f8qvumd7taOII0aSlp648SIfMw59WdUUtup5CnDYOcX1sUdivAj20m2PIDK6f+KWZ+7YKxJqCzJMH4GGlQvuDIhRKNT9oHfZgnYCCAmjXmJBtWyD052qqrkzOSn0/e9TKbjlTnTNcrIno3XDQ7xG+79vOD2GZMNopsKogWNxUdLFRu44ClKLRb4Xe00eVrANtBkv+mSJFFJS1Gxv611hpdGI2S0v1H+KvB26O7vuzGhZ/AevRemGhXQ5V5vwNEqXnVRVkBRszLKeN/+rxM436xQyVQGJMG+sVECAwEAAaMhMB8wHQYDVR0OBBYEFLlRBSxxgmNPObCFrl+hSsbcvRkcMA0GCSqGSIb3DQEBCwUAA4IBAQB+UQFTNs6BUY3AIGkS2ZRuZgJsNEr/ZEM4aCs2domd2Oqj7+5iWsnPh5CugFnI4nd+ZLgKVHSD6acQ27we+eNY6gxfpQCY1fiN/uKOOsA0If8IbPdBEhtPerRgPJFXLHaYVqD8UYDo5KNCcoB4Kh8nvCWRGPUUHPRqp7AnAcVrcbiXA/bmMCnFWuNNahcaAKiJTxYlKDaDIiPN35yECYbDj0PBWJUxobrvj5I275jbikkp8QSLYnSU/v7dMDUbxSLfZ7zsTuaF2Qx+L62PsYTwLzIFX3M8EMSQ6h68TupFTi5n0M2yIXQgoRoNEDWNJZ/aZMY/gqT02GQGBWrh+/vJ"]},{"kty":"RSA","use":"sig","kid":"DqUu8gf-nAgcyjP3-SuplNAXAnc","x5t":"DqUu8gf-nAgcyjP3-SuplNAXAnc","n":"1n7-nWSLeuWQzBRlYSbS8RjvWvkQeD7QL9fOWaGXbW73VNGH0YipZisPClFv6GzwfWECTWQp19WFe_lASka5-KEWkQVzCbEMaaafOIs7hC61P5cGgw7dhuW4s7f6ZYGZEzQ4F5rHE-YNRbvD51qirPNzKHk3nji1wrh0YtbPPIf--NbI98bCwLLh9avedOmqESzWOGECEMXv8LSM-B9SKg_4QuBtyBwwIakTuqo84swTBM5w8PdhpWZZDtPgH87Wz-_WjWvk99AjXl7l8pWPQJiKNujt_ck3NDFpzaLEppodhUsID0ptRA008eCU6l8T-ux19wZmb_yBnHcV3pFWhQ","e":"AQAB","x5c":["MIIC8TCCAdmgAwIBAgIQYVk/tJ1e4phISvVrAALNKTANBgkqhkiG9w0BAQsFADAjMSEwHwYDVQQDExhsb2dpbi5taWNyb3NvZnRvbmxpbmUudXMwHhcNMjAxMjIxMDAwMDAwWhcNMjUxMjIxMDAwMDAwWjAjMSEwHwYDVQQDExhsb2dpbi5taWNyb3NvZnRvbmxpbmUudXMwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDWfv6dZIt65ZDMFGVhJtLxGO9a+RB4PtAv185ZoZdtbvdU0YfRiKlmKw8KUW/obPB9YQJNZCnX1YV7+UBKRrn4oRaRBXMJsQxppp84izuELrU/lwaDDt2G5bizt/plgZkTNDgXmscT5g1Fu8PnWqKs83MoeTeeOLXCuHRi1s88h/741sj3xsLAsuH1q9506aoRLNY4YQIQxe/wtIz4H1IqD/hC4G3IHDAhqRO6qjzizBMEznDw92GlZlkO0+AfztbP79aNa+T30CNeXuXylY9AmIo26O39yTc0MWnNosSmmh2FSwgPSm1EDTTx4JTqXxP67HX3BmZv/IGcdxXekVaFAgMBAAGjITAfMB0GA1UdDgQWBBQ2r//lgTPcKughDkzmCtRlw+P9SzANBgkqhkiG9w0BAQsFAAOCAQEAsFdRyczNWh/qpYvcIZbDvWYzlrmFZc6blcUzns9zf7sUWtQZrZPu5DbetV2Gr2r3qtMDKXCUaR+pqoy3I2zxTX3x8bTNhZD9YAgAFlTLNSydTaK5RHyB/5kr6B7ZJeNIk3PRVhRGt6ybCJSjV/VYVkLR5fdLP+5GhvBESobAR/d0ntriTzp7/tLMb/oXx7w5Hu1m3I8rpMocoXfH2SH1GLmMXj6Mx1dtwCDYM6bsb3fhWRz9O9OMR6QNiTnq8q9wn1QzBAnRcswYzT1LKKBPNFSasCvLYOCPOZCL+W8N8jqa9ZRYNYKWXzmiSptgBEM24t3m5FUWzWqoLu9pIcnkPQ=="]},{"kty":"RSA","use":"sig","kid":"OzZ5Dbmcso9Qzt2ModGmihg30Bo","x5t":"OzZ5Dbmcso9Qzt2ModGmihg30Bo","n":"01re9a2BUTtNtdFzLNI-QEHW8XhDiDMDbGMkxHRIYXH41zBccsXwH9vMi0HuxXHpXOzwtUYKwl93ZR37tp6lpvwlU1HePNmZpJ9D-XAvU73x03YKoZEdaFB39VsVyLih3fuPv6DPE2qT-TNE3X5YdIWOGFrcMkcXLsjO-BCq4qcSdBH2lBgEQUuD6nqreLZsg-gPzSDhjVScIUZGiD8M2sKxADiIHo5KlaZIyu32t8JkavP9jM7ItSAjzig1W2yvVQzUQZA-xZqJo2jxB3g_fygdPUHK6UN-_cqkrfxn2-VWH1wMhlm90SpxTMD4HoYOViz1ggH8GCX2aBiX5OzQ6Q","e":"AQAB","x5c":["MIIC8TCCAdmgAwIBAgIQQrXPXIlUE4JMTMkVj+02YTANBgkqhkiG9w0BAQsFADAjMSEwHwYDVQQDExhsb2dpbi5taWNyb3NvZnRvbmxpbmUudXMwHhcNMjEwMzEwMDAwMDAwWhcNMjYwMzEwMDAwMDAwWjAjMSEwHwYDVQQDExhsb2dpbi5taWNyb3NvZnRvbmxpbmUudXMwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDTWt71rYFRO0210XMs0j5AQdbxeEOIMwNsYyTEdEhhcfjXMFxyxfAf28yLQe7Fcelc7PC1RgrCX3dlHfu2nqWm/CVTUd482Zmkn0P5cC9TvfHTdgqhkR1oUHf1WxXIuKHd+4+/oM8TapP5M0Tdflh0hY4YWtwyRxcuyM74EKripxJ0EfaUGARBS4Pqeqt4tmyD6A/NIOGNVJwhRkaIPwzawrEAOIgejkqVpkjK7fa3wmRq8/2Mzsi1ICPOKDVbbK9VDNRBkD7FmomjaPEHeD9/KB09QcrpQ379yqSt/Gfb5VYfXAyGWb3RKnFMwPgehg5WLPWCAfwYJfZoGJfk7NDpAgMBAAGjITAfMB0GA1UdDgQWBBTECjBRANDPLGrn1p7qtwswtBU7JzANBgkqhkiG9w0BAQsFAAOCAQEAq1Ib4ERvXG5kiVmhfLOpun2ElVOLY+XkvVlyVjq35rZmSIGxgfFc08QOQFVmrWQYrlss0LbboH0cIKiD6+rVoZTMWxGEicOcGNFzrkcG0ulu0cghKYID3GKDTftYKEPkvu2vQmueqa4t2tT3PlYF7Fi2dboR5Y96Ugs8zqNwdBMRm677N/tJBk53CsOf9NnBaxZ1EGArmEHHIb80vODStv35ueLrfMRtCF/HcgkGxy2U8kaCzYmmzHh4zYDkeCwM3Cq2bGkG+Efe9hFYfDHw13DzTR+h9pPqFFiAxnZ3ofT96NrZHdYjwbfmM8cw3ldg0xQzGcwZjtyYmwJ6sDdRvQ=="]}]}"""

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


# Azure AD settings
AZURE_AD_TENANT_ID = os.getenv("AZURE_AD_TENANT_ID", None)
AZURE_AD_CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID", None)
AZURE_AD_SECRET = os.getenv("AZURE_AD_SECRET", None)
