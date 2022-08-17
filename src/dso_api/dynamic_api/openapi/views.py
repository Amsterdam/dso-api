"""Extensions for the OpenAPI schema generator, that provides application-specific descriptions.

The main logic can be found in :mod:`rest_framework_dso.openapi`.
"""
from copy import copy
from functools import wraps
from typing import Callable, Optional, Union
from urllib.parse import urljoin

from django.conf import settings
from django.urls import URLPattern, URLResolver, get_resolver, get_urlconf
from django.utils.functional import lazy
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework import permissions, renderers
from rest_framework.schemas import get_schema_view
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset
from schematools.types import DatasetSchema

from rest_framework_dso.openapi import DSOSchemaGenerator

__all__ = (
    "get_openapi_json_view",
    "DynamicApiSchemaGenerator",
)


class DSOSwaggerView(SpectacularSwaggerView):
    """Overwritten SwaggerUI to support Azure OAuth."""

    template_name_js = "dso_api/dynamic_api/swagger_ui.js"
    schema = None  # exclude from schema detection

    def get(self, request, *args, **kwargs):
        if self.url.startswith("?"):
            # Better visual appearance on the UI page
            self.url = f"{request.path}{self.url}"
        return super().get(request, *args, **kwargs)


class DynamicApiSchemaGenerator(DSOSchemaGenerator):
    """This further extends the generic schema generator from :mod:`rest_framework_dso`
    with the application-specific knowledge found in DSO-API.
    """

    # Provide the missing data that DRF get_schema_view() doesn't yet offer
    defaultScope = {}
    if settings.OAUTH_DEFAULT_SCOPE:
        defaultScope = {settings.OAUTH_DEFAULT_SCOPE: "Toegang Applicatie"}
    schema_overrides = {
        # While drf_spectacular parses authentication_classes, it won't
        # recognize oauth2 nor detect a remote authenticator. Adding manually:
        "security": [{"oauth2": []}],
        "components": {
            "securitySchemes": {
                "oauth2": {
                    "type": "oauth2",
                    "flows": {
                        "implicit": {
                            "authorizationUrl": settings.OAUTH_URL,
                            "scopes": defaultScope,
                        }
                    },
                }
            }
        },
    }

    if not settings.DEBUG:
        schema_overrides["servers"] = [{"url": settings.DATAPUNT_API_URL}]


def get_openapi_json_view(dataset: Dataset):
    # To reduce the OpenAPI endpoints in the view there are 2 possible stategies:
    # 1. Override the generator_class.get_schema() and set .endpoints manually.
    #    This requires overriding the inner workings for the generator,
    #    override EndpointEnumerator.should_include_endpoint() etc..
    # 2. Provide a new list of URL patterns.
    #
    dataset_schema: DatasetSchema = dataset.schema

    # The second strategy is chosen here to keep the whole endpoint enumeration logic intact.
    # Patterns is a lazy object so it's not evaluated yet while the URLconf is being constructed.
    openapi_view = get_schema_view(
        title=dataset_schema.title or dataset_schema.id,
        description=dataset_schema.description or "",
        renderer_classes=[renderers.JSONOpenAPIRenderer],
        patterns=_lazy_get_dataset_patterns(dataset_schema.id),
        generator_class=DynamicApiSchemaGenerator,
        permission_classes=(permissions.AllowAny,),
        version=dataset_schema.version,
    )

    # Specific data to override in the OpenAPI
    openapi_overrides = {
        "info": {
            "license": {
                "name": dataset_schema.get("license", ""),
            },
        },
        "externalDocs": {
            "url": urljoin(
                settings.SPECTACULAR_SETTINGS["EXTERNAL_DOCS"]["url"],  # to preserve hostname
                f"/v1/docs/datasets/{dataset_schema.id}.html",
            )
        },
    }

    # As get_schema_view() offers no **initkwargs to the view, it's not possible to pass
    # additional parameters to the generator/view. Instead, our schema generator is directly
    # accessed here, and the override logic is reused.
    # The schema_override needs to be copied so the class attribute is not altered globally.
    schema_generator: DSOSchemaGenerator = openapi_view.view_initkwargs["schema_generator"]
    schema_generator.schema_overrides = {
        **openapi_overrides,
        **schema_generator.schema_overrides,
    }

    # Wrap the view in a "decorator" that shows the Swagger interface for browsers.
    return _swagger_on_browser(openapi_view)


def _swagger_on_browser(openapi_view):
    """A 'decorator' that shows the swagger interface on browser requests.
    This is a separate function to reduce the closure context data.
    """
    # The ?format=json isn't really needed, but makes the fetch/XMLHttpRequest explicit
    # to request the OpenAPI JSON and avoids any possible browser-interaction.
    swagger_view = DSOSwaggerView.as_view(url="?format=json")

    @wraps(openapi_view)
    def _switching_view(request):
        is_browser = "text/html" in request.headers.get("Accept", "")
        format = request.GET.get("format", "")
        if not is_browser or format == "json":
            # Not a browser, give the JSON view.
            return openapi_view(request)
        else:
            # Browser that accepts HTML, showing the swagger view.
            # This doesn't redirect to /swagger/
            # Using the view so the addressbar path remains the same.
            return swagger_view(request)

    return _switching_view


def get_dataset_patterns(dataset_id: str) -> list[Union[URLPattern, URLResolver]]:
    """Find the URL patterns for a specific dataset.

    This returns a subtree of the URLConf that only contains the
    patterns as if this application only hosted those specific URLs.
    """
    from ..views import DynamicApiViewSet

    return _get_patterns(
        matcher=lambda view_cls: (
            issubclass(view_cls, DynamicApiViewSet) and view_cls.dataset_id == dataset_id
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
