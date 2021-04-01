"""Extensions for the OpenAPI schema generator, that provides application-specific descriptions.

The main logic can be found in :mod:`rest_framework_dso.openapi`.
"""
from copy import copy
from typing import Callable, List, Optional, Union

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver, get_urlconf
from django.utils.functional import lazy
from rest_framework import permissions, renderers
from rest_framework.schemas import get_schema_view
from rest_framework.views import APIView

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


def get_openapi_json_view(*dataset_ids):
    """Provide the OpenAPI view, which renders as JSON."""
    return _get_openapi_view(*dataset_ids, renderer_classes=[renderers.JSONOpenAPIRenderer])


def get_openapi_yaml_view(*dataset_ids):
    """Provide the OpenAPI view, which renders as YAML."""
    return _get_openapi_view(*dataset_ids, renderer_classes=[renderers.OpenAPIRenderer])


def _get_openapi_view(*dataset_ids, renderer_classes=None):
    # To reduce the OpenAPI endpoints in the view there are 2 possible stategies:
    # 1. Override the generator_class.get_schema() and set .endpoints manually.
    #    This requires overriding the inner workings for the generator,
    #    override EndpointEnumerator.should_include_endpoint() etc..
    # 2. Provide a new list of URL patterns.
    #
    # The second strategy is chosen here to keep the whole endpoint enumeration logic intact.
    # Patterns is a lazy object so it's not evaluated yet while the URLconf is being constructed.
    patterns = None if not dataset_ids else _lazy_get_dataset_patterns(*dataset_ids)

    return get_schema_view(
        renderer_classes=renderer_classes,
        patterns=patterns,
        generator_class=ExtendedSchemaGenerator,
        permission_classes=(permissions.AllowAny,),
    )


def get_dataset_patterns(*dataset_ids) -> List[Union[URLPattern, URLResolver]]:
    """Find the URL patterns for a specific dataset.

    This returns a subtree of the URLConf that only contains the
    patterns as if this application only hosted those specific URLs.
    """
    from .views import DynamicApiViewSet

    dataset_ids = set(dataset_ids)
    return _get_patterns(
        matcher=lambda view_cls: (
            issubclass(view_cls, DynamicApiViewSet) and view_cls.dataset_id in dataset_ids
        )
    )


_lazy_get_dataset_patterns = lazy(get_dataset_patterns, list)


def _get_patterns(matcher: Callable[[APIView], bool], patterns: Optional[list] = None, prefix=""):
    """Find a subset of URL patterns, based on a matching predicate."""
    if patterns is None:
        resolver = get_resolver(get_urlconf())
        patterns = resolver.url_patterns

    matches = []

    # This code is inspired by DRF's EndpointEnumerator.get_api_endpoints().
    # However, instead of returning the paths, it collects the URL patterns.
    for pattern in patterns:
        path_regex = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLPattern):
            # Inspect the class-based-view for inclusion
            if hasattr(pattern.callback, "cls") and matcher(pattern.callback.cls):
                matches.append(pattern)

        elif isinstance(pattern, URLResolver):
            # Recurse into the 'include' section to find matches.
            sub_patterns = _get_patterns(matcher, patterns=pattern.url_patterns, prefix=path_regex)
            if sub_patterns:
                # Return a root object, but only include the objects that matched.
                root = copy(pattern)
                root.__dict__["url_patterns"] = sub_patterns
                matches.append(root)
        else:
            raise NotImplementedError(f"Unknown URL pattern type: {pattern!r}")

    return matches
