import django_healthchecks.urls
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic import RedirectView

import dso_api.dynamic_api.urls
from rest_framework_dso import views


def _raise_runtime_error(request):
    raise RuntimeError("Testing 500 error.")


docs_index_redirect = RedirectView.as_view(pattern_name="dynamic_api:docs-index", permanent=True)

urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    path("500-test/", _raise_runtime_error),
    path("v1", include(dso_api.dynamic_api.urls), name="root"),
    path("v1/", RedirectView.as_view(url="/v1", permanent=True), name="root-tailing-slash"),
    path("", RedirectView.as_view(url="/v1"), name="root-redirect"),
    path("v1/docs/", docs_index_redirect),
    path("v1/docs/datasets/", docs_index_redirect),
    path("v1/docs/datasets/index.html", docs_index_redirect),
    re_path(
        r"^.*/{2,}.*$",
        views.multiple_slashes,
        name="error-trailing-slashes",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


handler400 = views.bad_request
handler404 = views.not_found
handler500 = views.server_error


if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([path("__debug__/", include(debug_toolbar.urls))])
