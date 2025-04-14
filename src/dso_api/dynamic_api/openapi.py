"""Extensions for the OpenAPI schema generator, that provides application-specific descriptions.

The main logic can be found in :mod:`rest_framework_dso.openapi`.
"""

from collections.abc import Callable
import copy
import os
from functools import wraps
import logging
from urllib.parse import urljoin, urlparse

import drf_spectacular.plumbing
from django.conf import settings
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.urls import URLPattern, URLResolver, get_resolver, get_urlconf
from django.utils.functional import lazy
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers


from rest_framework import permissions, renderers
from rest_framework.response import Response
from rest_framework.schemas import get_schema_view
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset
from schematools.permissions import UserScopes
from schematools.types import DatasetSchema

from dso_api.dynamic_api.views import DynamicApiViewSet

from rest_framework_dso.openapi import DSOSchemaGenerator
from rest_framework_dso.renderers import BrowsableAPIRenderer, HALJSONRenderer

from .datasets import get_active_datasets

import logging
logger = logging.getLogger(__name__)

__all__ = (
    "get_openapi_view",
    "DynamicApiSchemaGenerator",
)


def build_mock_request(method, path, view, original_request, **kwargs):
    """Fix the request object that drf-spectacular generates for OpenAPI detection"""
    request = drf_spectacular.plumbing.build_mock_request(
        method, path, view, original_request, **kwargs
    )
    request.accepted_renderer = HALJSONRenderer()
    request.accept_crs = None  # for DSOSerializer, expects to be used with DSOViewMixin
    request.response_content_crs = None

    # Make sure all fields are displayed in the OpenAPI spec:
    request.user_scopes = UserScopes(query_params={}, request_scopes=[])
    request.user_scopes.has_any_scope = lambda scopes: True
    request.user_scopes.has_all_scopes = lambda scopes: True
    return request


class openAPIBrowserView(APIView):
    """Browsable API View."""

    # Restrict available formats browsable API
    renderer_classes = [BrowsableAPIRenderer]

    name = "DSO-API"
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
    )
    authorization_grantor = None
    response_formatter = "openapi_formatter"

    def get(self, request, *args, **kwargs):
        return Response()


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

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request=request, public=public)

        if not request or not hasattr(request, 'path') or not request.path:
             return schema # Cannot process without request context

        # Skip processing for the root openapi.json and openapi.yaml requests
        #if request.path == '/v1/openapi.json/' or request.path == '/v1/openapi.yaml/':
        #     return schema
        
        # modify request.path to ensure it ends with a slash and removes openapi.json and openapi.yaml
        cleaned_path = request.path.replace('/openapi.json','').replace('/openapi.yaml','')
        if not cleaned_path.endswith('/') and cleaned_path != '/v1':
            cleaned_path += '/'
        
        current_doc_dir = os.path.dirname(cleaned_path)
        logging.info(f"Current doc dir: {current_doc_dir}")
        logging.info(f"Current request path: {cleaned_path}")
        

        # Ensure 'servers' field reflects this base path if not already set correctly
        if 'servers' not in schema:
            base_url = f"{request.scheme}://{request.get_host()}"
            final_server_url = urljoin(base_url, current_doc_dir)
            schema['servers'] = [{'url': final_server_url, 'description': 'Dynamically determined server URL for this dataset'}]
        

        # Make the paths within the 'paths' object relative to the server URL.
        if schema.get('paths'):
            original_paths = schema.get('paths', {})
            modified_paths = {}
            for path, path_item in original_paths.items():
                # Ensure path starts with '/' and remove trailing slash for consistent comparison with current_doc_dir
                absolute_path = path if path.startswith('/') else '/' + path
                absolute_path = absolute_path.rstrip('/')
                # Check if the path starts with the directory of the current doc
                if absolute_path.startswith(current_doc_dir):
                    # e.g. /v1/aardgasverbruik/mra_liander/ -> /mra_liander
                    relative_path = absolute_path.replace(cleaned_path, "")
                    if relative_path.endswith('/'):
                        relative_path = relative_path[:-1]
                    if not relative_path.startswith('/'):
                        relative_path = '/' + relative_path
                    modified_paths[relative_path] = path_item
                else:
                    # Path doesn't start with the expected base path, keep it as is
                    logging.info(f"Path {path} does not start with {current_doc_dir}, keeping it as is.")
                    modified_paths[path] = path_item
            schema['paths'] = modified_paths
        return schema


def get_openapi_view(dataset, response_format: str = "json"):

    if not isinstance(dataset, Dataset):
        raise TypeError("Expected Dataset instance, got {type(dataset)}")
    dataset_schema: DatasetSchema = dataset.schema

    renderer_class = (
        renderers.JSONOpenAPIRenderer if response_format == "json" else renderers.OpenAPIRenderer
    )

    # Patterns is a lazy object so it's not evaluated yet while the URLconf is being constructed.
    openapi_view = get_schema_view(
        title=dataset_schema.title or dataset_schema.id,
        description=dataset_schema.description or "",
        renderer_classes=[renderer_class],
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
                settings.DATAPUNT_API_URL,  # to preserve hostname
                f"/v1/docs/datasets/{dataset.path}.html",
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
    return _html_on_browser(openapi_view, dataset_schema, response_format)


CACHE_DURATION = 60 * 60 * 24 * 7  # Seconds.


def _html_on_browser(openapi_view, dataset_schema, response_format: str = "json"):
    """A 'decorator' that shows the browsable interface on browser requests.
    This is a separate function to reduce the closure context data.
    """
    # The ?format=json isn't really needed, but makes the fetch/XMLHttpRequest explicit
    # to request the OpenAPI JSON and avoids any possible browser-interaction.
    browsable_view = openAPIBrowserView

    @wraps(openapi_view)
    def _switching_view(request):
        is_browser = "text/html" in request.headers.get("Accept", "")
        format = request.GET.get("format", "")
        path = request.path

        # Handle file downloads for openapi.json and openapi.yaml
        if path.endswith("openapi.json") or path.endswith("openapi.yaml"):
            view = vary_on_headers("Accept", "format")(openapi_view)
            view = cache_page(CACHE_DURATION)(view)
            response = view(request)

            # Set content disposition for download
            filename = "openapi.json" if path.endswith(".json") else "openapi.yaml"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        if not is_browser or format == "json" or format == "yaml":
            # Not a browser, give the JSON/YAML view
            # Add accept and format to the Vary header so cache is
            # triggered on the json response only
            view = vary_on_headers("Accept", "format")(openapi_view)
            view = cache_page(CACHE_DURATION)(view)
            return view(request)
        else:
            # Browser that accepts HTML, showing the browsable view.
            # Using the view so the addressbar path remains the same.
            return browsable_view().as_view(
                name=dataset_schema.title or dataset_schema.id,
                description=dataset_schema.description or "",
                authorization_grantor=dataset_schema.data.get("authorizationGrantor", None),
            )(request)

    return _switching_view


def get_dataset_patterns(dataset_id: str) -> list[URLPattern | URLResolver]:
    """Find the URL patterns for a specific dataset.

    This returns a subtree of the URLConf that only contains the
    patterns as if this application only hosted those specific URLs.
    """
    from .views import DynamicApiViewSet

    return _get_patterns(
        matcher=lambda view_cls: (
            issubclass(view_cls, DynamicApiViewSet) and view_cls.dataset_id == dataset_id
        )
    )

_lazy_get_dataset_patterns = lazy(get_dataset_patterns, list)


def _get_patterns(matcher: Callable[[APIView], bool], patterns: list | None = None, prefix=""):
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
                root = copy.copy(pattern)
                root.__dict__["url_patterns"] = sub_patterns
                matches.append(root)
        else:
            raise NotImplementedError(f"Unknown URL pattern type: {pattern!r}")

    return matches

def merge_openapi_schemas(schemas: list[dict]) -> dict:
    """Merge multiple OpenAPI schemas into a single one."""
    if not schemas:
        return {}

    combined_schema = copy.deepcopy(schemas[0])

    for schema in schemas[1:]:
        for path, path_item in schema.get("paths", {}).items():
            if path not in combined_schema["paths"]:
                combined_schema["paths"][path] = path_item
            else:
                combined_schema["paths"][path].update(path_item)

        for comp_type, components in schema.get("components", {}).items():
            if comp_type not in combined_schema["components"]:
                combined_schema["components"][comp_type] = {}
            combined_schema["components"][comp_type].update(components)

    return combined_schema


class CombinedSchemaView(APIView):
    """
    View that generates a combined OpenAPI schema for all active datasets.
    """
    permission_classes = (permissions.AllowAny,)
    cache_timeout = getattr(settings, 'OPENAPI_CACHE_TIMEOUT', 300)
    format = None  # Will be set via as_view()
    renderer_classes = None  # Will be determined dynamically

    def __init__(self, *args, **kwargs):
        self.format = kwargs.pop('format', 'json')
        super().__init__(*args, **kwargs)
        self.renderer_classes = [
            renderers.JSONOpenAPIRenderer if self.format == 'json' 
            else renderers.OpenAPIRenderer
        ]
        logger.info(f"CombinedSchemaView initialized with format: {self.format}")
        logger.info(f"Renderer classes: {self.renderer_classes}")

    def get_schema_generator(self, request):
        """Get the schema generator instance with proper patterns"""
        active_datasets = list(get_active_datasets())
        active_dataset_ids = {ds.schema.id for ds in active_datasets}

        def combined_matcher(view_cls):
            return (
                issubclass(view_cls, DynamicApiViewSet) and 
                getattr(view_cls, 'dataset_id', None) in active_dataset_ids
            )

        patterns = _get_patterns(matcher=combined_matcher)
        return DynamicApiSchemaGenerator(patterns=patterns)

    @method_decorator(cache_page(cache_timeout))
    @method_decorator(vary_on_headers("Accept"))
    def get(self, request, *args, **kwargs):
        """Generate and return the combined OpenAPI schema"""
        try:
            generator = self.get_schema_generator(request)
            schema = generator.get_schema(request=request, public=True)
            
            if schema:
                schema.update({
                    "info": {
                        "title": "DSO-API",
                        "version": "v1",
                        "description": "OpenAPI specification for all active datasets.",
                    },
                    "servers": [{
                        "url": f"{settings.DATAPUNT_API_URL}v1/",
                        "description": "DSO-API",
                    }],
                })

            # Use the appropriate renderer based on format
            if self.format == 'yaml':
                response = Response(schema or {}, content_type='application/yaml')
            else:
                response = Response(schema or {}, content_type='application/json')

            if request.path.endswith(('.json', '.yaml')):
                ext = 'json' if request.path.endswith('.json') else 'yaml'
                response['Content-Disposition'] = f'attachment; filename="openapi.{ext}"'
                response['X-Content-Type-Options'] = 'nosniff'

            return response

        except Exception as e:
            return JsonResponse({
                "error": "Failed to generate OpenAPI specification",
                "detail": str(e)
            }, status=500)
