import sys
from importlib import import_module, reload

from django.conf import settings
from django.urls import clear_url_caches, get_urlconf


def reload_urlconf(urlconf_name=None):
    if urlconf_name is None:
        urlconf_name = get_urlconf() or settings.ROOT_URLCONF

    # Reload the global top-level module
    if urlconf_name in sys.modules:
        reload(sys.modules[urlconf_name])
    else:
        import_module(urlconf_name)

    # Clear the Django lru caches
    clear_url_caches()
