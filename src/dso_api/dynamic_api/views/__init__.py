"""All views for the dynamically generated API, split by protocol type."""
from .api import DynamicApiViewSet, reload_patterns, viewset_factory
from .mvt import DatasetMVTIndexView, DatasetMVTView
from .oauth import DSOSwaggerView, oauth2_redirect
from .wfs import DatasetWFSIndexView, DatasetWFSView

__all__ = (
    "DynamicApiViewSet",
    "DatasetMVTView",
    "DatasetMVTIndexView",
    "DatasetWFSView",
    "DatasetWFSIndexView",
    "DSOSwaggerView",
    "viewset_factory",
    "reload_patterns",
    "oauth2_redirect",
)
