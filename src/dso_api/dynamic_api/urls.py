from django.urls import clear_url_caches, include, path

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

urlpatterns = router.urls


def refresh(router_urls):
    """Refresh the URL patterns in this file, and reload the URLConf."""
    global urlpatterns
    urlpatterns = get_patterns(router_urls)

    clear_url_caches()
