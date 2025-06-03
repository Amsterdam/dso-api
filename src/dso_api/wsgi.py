"""
WSGI config for dso_api project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/wsgi/
"""

import os
import sys

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dso_api.settings")

application = get_wsgi_application()
application = WhiteNoise(application, root=settings.STATIC_ROOT)

# Warm-up Django ahead of time instead of lazy-apps
# From: http://uwsgi-docs.readthedocs.org/en/latest/articles/TheArtOfGracefulReloading.html#dealing-with-ultra-lazy-apps-like-django
application(
    {
        "REQUEST_METHOD": "GET",
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "80",
        "PATH_INFO": "/v1/",
        "wsgi.input": sys.stdin,
        "wsgi.url_scheme": "http",
        "wsgi.errors": sys.stderr,
        "wsgi.version": (1, 0),
    },
    lambda x, y: None,
)
