import django_healthchecks.urls
from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from rest_framework import exceptions

import dso_api.dynamic_api.urls
from dso_api.dynamic_api.oas3 import get_openapi_yaml_view
from rest_framework_dso.views import multiple_trailing_slashes

urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    path("v1/", include(dso_api.dynamic_api.urls)),
    path("v1/openapi.yaml", get_openapi_yaml_view(), name="openapi.yaml",),
    path("", RedirectView.as_view(url="/v1/"), name="root-redirect"),
    re_path(r"^.*/{2,}.*", multiple_trailing_slashes, name="error-trailing-slashes",),
]

handler400 = exceptions.bad_request
handler500 = exceptions.server_error


if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([path("__debug__/", include(debug_toolbar.urls))])
