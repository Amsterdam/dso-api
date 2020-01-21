import os

import environ
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

env = environ.Env()

# -- Environment

BASE_DIR = str(environ.Path(__file__) - 2)
DEBUG = env.bool('DJANGO_DEBUG', True)

# Paths
STATIC_URL = '/dso-api/static/'
STATIC_ROOT = '/static/'

# -- Security

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str('SECRET_KEY', 'insecure')

SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', not DEBUG)

INTERNAL_IPS = ('127.0.0.1', '0.0.0.0')


# -- Application definition

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'corsheaders',
    'django_filters',
    'rest_framework',
    'rest_framework_gis',
    'rest_framework_swagger',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if DEBUG:
    INSTALLED_APPS += [
        'debug_toolbar',
        'django_extensions',
    ]
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

CORS_ORIGIN_ALLOW_ALL = True

ROOT_URLCONF = 'dso_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'OPTIONS': {
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

if not DEBUG:
    # Keep templates in memory
    TEMPLATES[0]['OPTIONS']['loaders'] = [
        ('django.template.loaders.cached.Loader', TEMPLATES[0]['OPTIONS']['loaders']),
    ]

WSGI_APPLICATION = 'dso_api.wsgi.application'

# -- Services

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])

DATABASES = {
    'default': env.db_url("DATABASE_URL", default="postgres://dso_api:insecure@database/dso_api"),
}
DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'

locals().update(env.email_url(default='smtp://'))

SENTRY_DSN = env.str('SENTRY_DSN', default='')
SENTRY_ENVIRONMENT = env.str('SENTRY_ENVIRONMENT', default='dev')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()]
    )


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'console': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },

    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'console',
        },
    },

    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },

    'loggers': {
        # 'django.db.backends': {
        #     'level': 'DEBUG',
        #     'handlers': ['console'],
        # },
        'dso_api': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}


# -- Third party app settings

REST_FRAMEWORK = dict(
    PAGE_SIZE=20,
    MAX_PAGINATE_BY=20,

    UNAUTHENTICATED_USER={},
    UNAUTHENTICATED_TOKEN={},

    DEFAULT_PAGINATION_CLASS='djangorestframework_dso.pagination.DSOPageNumberPagination',

    DEFAULT_AUTHENTICATION_CLASSES=[
        # 'rest_framework.authentication.BasicAuthentication',
        # 'rest_framework.authentication.SessionAuthentication',
    ],
    DEFAULT_RENDERER_CLASSES=[
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer'
    ],
    DEFAULT_FILTER_BACKENDS=[
        'django_filters.rest_framework.backends.DjangoFilterBackend',
    ],
    COERCE_DECIMAL_TO_STRING=True,
)

SWAG_PATH = env.str(
    "SWAG_PATH", default='127.0.0.1:8000/docs' if DEBUG else 'acc.api.data.amsterdam.nl/docs'
)

SWAGGER_SETTINGS = {
    'exclude_namespaces': [],
    'api_version': '0.1',
    'api_path': '/',

    'enabled_methods': [
        'get',
    ],

    'api_key': '',
    'USE_SESSION_AUTH': False,
    'VALIDATOR_URL': None,

    'is_authenticated': False,
    'is_superuser': False,

    'unauthenticated_user': 'django.contrib.auth.models.AnonymousUser',
    'permission_denied_handler': None,
    'resource_access_handler': None,

    'protocol': 'https' if not DEBUG else '',
    'base_path': SWAG_PATH,

    'info': {
        'contact': 'datapunt@amsterdam.nl',
        'description': 'This is the generic DSO-compatible API server.',
        'license': 'Not known yet',
        'termsOfServiceUrl': 'https://data.amsterdam.nl/terms/',
        'title': 'Tellus',
    },

    'doc_expansion': 'list',
}
