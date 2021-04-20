"""All views for the dynamically generated API, split by protocol type."""
from .api import DynamicApiViewSet, reload_patterns, viewset_factory
from .mvt import DatasetMVTIndexView, DatasetMVTView
from .wfs import DatasetWFSIndexView, DatasetWFSView
from .login import oauth2_redirect, generic_openapi

__all__ = (
    "DynamicApiViewSet",
    "DatasetMVTView",
    "DatasetMVTIndexView",
    "DatasetWFSView",
    "DatasetWFSIndexView",
    "viewset_factory",
    "reload_patterns",
    "oauth2_redirect",
    "generic_openapi",
)
