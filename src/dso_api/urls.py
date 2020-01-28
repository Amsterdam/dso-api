import django_healthchecks.urls
from django.conf import settings
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

import dso_api.dynamic_api.urls

schema_view = get_schema_view(
    openapi.Info(
        title="DSO-API",
        default_version='v1',
        description="This is the generic DSO-compatible API server.",
        terms_of_service="https://data.amsterdam.nl/",
        contact=openapi.Contact(email="datapunt@amsterdam.nl"),
        license=openapi.License(name="CC0 1.0 Universal"),
    ),
    url="{}handelsregister/".format(settings.DATAPUNT_API_URL),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('status/health/', include(django_healthchecks.urls)),
    path('v1/', include(dso_api.dynamic_api.urls)),

    re_path(r'^openapi(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0)),
    path('', schema_view.with_ui('swagger', cache_timeout=None)),
]

if 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([
        path('__debug__/', include(debug_toolbar.urls)),
    ])
