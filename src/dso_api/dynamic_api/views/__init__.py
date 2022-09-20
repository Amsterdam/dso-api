"""All views for the dynamically generated API, split by protocol type."""
from .api import DynamicApiViewSet, viewset_factory
from .index import APIIndexView
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
    "oauth2_redirect",
    "viewset_factory",
)
