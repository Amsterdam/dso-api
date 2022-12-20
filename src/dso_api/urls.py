import django_healthchecks.urls
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.generic import RedirectView

import dso_api.dynamic_api.urls
from rest_framework_dso import views


def _raise_runtime_error(request):
    raise RuntimeError("Testing 500 error.")


urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    path("500-test/", _raise_runtime_error),
    path("v1/", include(dso_api.dynamic_api.urls)),
    path("", RedirectView.as_view(url="/v1/"), name="root-redirect"),
    path("v1/docs/", RedirectView.as_view(url="/v1/docs/index.html", permanent=True)),
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
