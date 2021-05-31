"""All views for the dynamically generated API, split by protocol type."""
from .api import APIIndexView, DynamicApiViewSet, reload_patterns, viewset_factory
from .mvt import DatasetMVTIndexView, DatasetMVTSingleView, DatasetMVTView
from .oauth import oauth2_redirect
from .wfs import DatasetWFSIndexView, DatasetWFSView

__all__ = (
    "DynamicApiViewSet",
    "APIIndexView",
    "DatasetMVTView",
    "DatasetMVTIndexView",
    "DatasetMVTSingleView",
    "DatasetWFSView",
    "DatasetWFSIndexView",
    "viewset_factory",
    "reload_patterns",
    "oauth2_redirect",
)
