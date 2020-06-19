from django.urls import include, path

from dso_api.dynamic_api.routers import DynamicRouter
from dso_api.lib.urls import reload_urlconf

from . import views


def get_patterns(router_urls):
    """Generate the actual URL patterns for this file."""
    return [
        path("reload/", views.reload_patterns),
        path("wfs/<dataset_name>/", views.DatasetWFSView.as_view()),
        path("csv/<dataset_name>/<table_name>/", views.DatasetCSVView.as_view()),
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
