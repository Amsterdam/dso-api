import sys
from importlib import reload

from django.urls import clear_url_caches, include, path, get_urlconf

from dso_api.dynamic_api.routers import DynamicRouter
from . import views


def get_patterns(router_urls):
    """Generate the actual URL patterns for this file."""
    return [
        path('reload/', views.reload_patterns),
        path('', include(router_urls)),
    ]


app_name = 'dynamic_api'

router = DynamicRouter()

urlpatterns = get_patterns(router.urls)


def refresh_urls(router_instance):
    """Refresh the URL patterns in this file, and reload the URLConf."""
    from django.conf import settings

    if router_instance is not router:
        raise RuntimeError("Reloading causes duplicate router instances.")

    # Replace URLpatterns in this file
    global urlpatterns
    urlpatterns = get_patterns(router.urls)

    # Reload the global top-level module
    #urlconf_name = get_urlconf() or settings.ROOT_URLCONF
    #reload(sys.modules[urlconf_name])
    clear_url_caches()
