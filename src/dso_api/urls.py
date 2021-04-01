import django_healthchecks.urls
from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic import RedirectView

import dso_api.dynamic_api.urls
from rest_framework_dso import views

urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    path("v1/", include(dso_api.dynamic_api.urls)),
    path("", RedirectView.as_view(url="/v1/"), name="root-redirect"),
    re_path(
        r"^.*/{2,}.*$",
        views.multiple_slashes,
        name="error-trailing-slashes",
    ),
]

handler400 = views.bad_request
handler404 = views.not_found
handler500 = views.server_error


if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([path("__debug__/", include(debug_toolbar.urls))])
