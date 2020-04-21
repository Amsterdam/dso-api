import django_healthchecks.urls
from django.conf import settings
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework import exceptions, permissions, renderers
from rest_framework.schemas import get_schema_view
from rest_framework.utils.formatting import dedent

# import dso_api.datasets.urls
import dso_api.dynamic_api.urls
from rest_framework_dso.openapi import DSOSchemaGenerator


class ExtendedSchemaGenerator(DSOSchemaGenerator):
    """drf_spectacular also provides 'components' which DRF doesn't do."""

    # Provide the missing data that DRF get_schema_view() doesn't yet offer.:
    schema_overrides = {
        "info": {
            "title": "DSO-API",
            "version": "v1",
            "description": dedent(dso_api.dynamic_api.urls.router.APIRootView.__doc__),
            # These fields can't be specified in get_schema_view():
            "termsOfService": "https://data.amsterdam.nl/",
            "contact": {"email": "datapunt@amsterdam.nl"},
            "license": {"name": "CC0 1.0 Universal"},
        },
        # While drf_spectacular parses authentication_classes, it won't
        # recognize oauth2 nor detect a remote authenticator. Adding manually:
        "security": [{"oauth2": []}],
        "components": {
            "securitySchemes": {
                "oauth2": {
                    "type": "oauth2",
                    "flows": {
                        "implicit": {
                            "authorizationUrl": "https://api.data.amsterdam.nl/oauth2/authorize",
                            "scopes": {"HR/R": "Toegang HR"},
                        }
                    },
                }
            }
        },
    }

    if not settings.DEBUG:
        schema_overrides["servers"] = [{"url": settings.DATAPUNT_API_URL}]


def _get_schema_view(renderer_classes=None):
    return get_schema_view(
        public=True,
        renderer_classes=renderer_classes,
        generator_class=ExtendedSchemaGenerator,
        permission_classes=(permissions.AllowAny,),
    )


urlpatterns = [
    path("status/health/", include(django_healthchecks.urls)),
    # path("datasets/", include(dso_api.datasets.urls)),
    path("v1/", include(dso_api.dynamic_api.urls)),
    # path("v1/", schema_view.with_ui("swagger", cache_timeout=0)),
    path(
        "v1/openapi.yaml",
        _get_schema_view(renderer_classes=[renderers.OpenAPIRenderer]),
        name="openapi.yaml",
    ),
    path(
        "v1/openapi.json",
        _get_schema_view(renderer_classes=[renderers.JSONOpenAPIRenderer]),
        name="openapi.json",
    ),
    path("", RedirectView.as_view(url="/v1/"), name="root-redirect"),
]

handler400 = exceptions.bad_request
handler500 = exceptions.server_error


if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns.extend([path("__debug__/", include(debug_toolbar.urls))])
