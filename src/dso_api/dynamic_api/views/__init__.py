"""All views for the dynamically generated API, split by protocol type."""

from .api import DynamicApiViewSet, viewset_factory
from .doc import DatasetDocView, DocsOverview
from .index import APIIndexView
from .mvt import DatasetMVTIndexView, DatasetMVTSingleView, DatasetMVTView, DatasetTileJSONView
from .oauth import oauth2_redirect
from .wfs import DatasetWFSIndexView, DatasetWFSView

__all__ = (
    "DynamicApiViewSet",
    "APIIndexView",
    "DatasetDocView",
    "DatasetMVTView",
    "DatasetMVTIndexView",
    "DatasetMVTSingleView",
    "DatasetTileJSONView",
    "DatasetWFSView",
    "DatasetWFSIndexView",
    "DocsOverview",
    "oauth2_redirect",
    "viewset_factory",
)
