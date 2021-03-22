import sys
from importlib import import_module, reload

from django.conf import settings
from django.urls import clear_url_caches, get_urlconf, include, path

from dso_api.dynamic_api.routers import DynamicRouter

from . import views


def get_patterns(router_urls):
    """Generate the actual URL patterns for this file."""
    return [
        path("reload/", views.reload_patterns),
        path("wfs/", views.DatasetWFSIndexView.as_view()),
        path("wfs/<dataset_name>/", views.DatasetWFSView.as_view()),
        path("", include(router_urls)),
    ]


app_name = "dynamic_api"

router = DynamicRouter()
router.initialize()

urlpatterns = get_patterns(router.urls)


def refresh_urls(router_instance):
    """Refresh the URL patterns in this file, and reload the URLConf."""

    if router_instance is not router:
        raise RuntimeError("Reloading causes duplicate router instances.")

    # Replace URLpatterns in this file
    global urlpatterns
    urlpatterns = get_patterns(router.urls)

    # Reload the global URLs to make this visible
    reload_urlconf()


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
