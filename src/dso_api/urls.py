import django_healthchecks.urls
from django.conf import settings
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

import dso_api.datasets.urls
import dso_api.dynamic_api.urls

schema_view = get_schema_view(
    openapi.Info(
        title="DSO-API",
        default_version="v1",
        description=(
            "This is the generic [DSO-compatible](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/) API server.\n"  # noqa E501
            "\n"
            "The following features are supported:\n"
            "* HAL-JSON based links, pagination and response structure.\n"
            "* Use `?expand=name1,name2` to sideload specific relations.\n"
            "* Use `?expand=true` to sideload all relations.\n"
            "\n"
            "The models in this server are generated from the Amsterdam Schema files.\n"
            "These are located at: https://github.com/Amsterdam/schemas"
        ),
        terms_of_service="https://data.amsterdam.nl/",
        contact=openapi.Contact(email="datapunt@amsterdam.nl"),
        license=openapi.License(name="CC0 1.0 Universal"),
    ),
    url=f"{settings.DATAPUNT_API_URL}v1/",
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    path("datasets/", include(dso_api.datasets.urls)),
    path("v1/", include(dso_api.dynamic_api.urls)),
    path("v1/", schema_view.with_ui("swagger", cache_timeout=0)),
    re_path(
        r"^v1/openapi(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
    ),
    path("", RedirectView.as_view(url="/v1/"), name="root-redirect"),
]

if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([path("__debug__/", include(debug_toolbar.urls))])
