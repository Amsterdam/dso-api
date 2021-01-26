from django.conf import settings
from rest_framework import permissions, renderers
from rest_framework.schemas import get_schema_view

from rest_framework_dso.openapi import DSOSchemaGenerator

__all__ = (
    "get_openapi_json_view",
    "get_openapi_yaml_view",
    "ExtendedSchemaGenerator",
)


class ExtendedSchemaGenerator(DSOSchemaGenerator):
    """drf_spectacular also provides 'components' which DRF doesn't do."""

    # Provide the missing data that DRF get_schema_view() doesn't yet offer.:
    schema_overrides = {
        "info": {
            "title": "DSO-API",
            "version": "v1",
            "description": """
This is the generic [DSO-compatible](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/) API server.

The following features are supported:

* HAL-JSON based links, pagination and response structure.
* Use `?_expandScope=name1,name2` to sideload specific relations.
* Use `?_expand=true` to sideload all relations.

The models in this server are generated from the Amsterdam Schema files.
These are located at:
[https://schemas.data.amsterdam.nl/datasets](https://schemas.data.amsterdam.nl/datasets)
""",  # noqa: E501
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
                            "authorizationUrl": f"{settings.DATAPUNT_API_URL}oauth2/authorize",
                            "scopes": {
                                "HR/R": "Toegang HR",
                                "BRK/RSN": "Bevragen Natuurlijke Kadastrale Subjecten.",
                                "BRK/RS": "Bevragen Kadastrale Subjecten.",
                                "BRK/RO": "Read kadastraal object",
                                "BRP/R": "Basisregister personen",
                                "FP/MDW": "Functieprofiel medewerker",
                            },
                        }
                    },
                }
            }
        },
    }

    if not settings.DEBUG:
        schema_overrides["servers"] = [{"url": settings.DATAPUNT_API_URL}]


def _get_openapi_view(renderer_classes=None):
    return get_schema_view(
        public=True,
        renderer_classes=renderer_classes,
        generator_class=ExtendedSchemaGenerator,
        permission_classes=(permissions.AllowAny,),
    )


def get_openapi_json_view():
    return _get_openapi_view(renderer_classes=[renderers.JSONOpenAPIRenderer])


def get_openapi_yaml_view():
    return _get_openapi_view(renderer_classes=[renderers.OpenAPIRenderer])
