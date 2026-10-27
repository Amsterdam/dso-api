"""All views for the dynamically generated API, split by protocol type."""

from .api import DynamicApiViewSet, viewset_factory
from .doc import DatasetDocView, DocsIndexView
from .index import APIIndexView
from .mvt import DatasetMVTIndexView, DatasetMVTSingleView, DatasetMVTView, DatasetTileJSONView
from .oauth import oauth2_redirect
from .ogc import (
    DatasetOGCIndexView,
    DatasetOGCRecordsIndexView,
    OGCRecordsCollectionDetailView,
    OGCRecordsCollectionView,
)
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
    "DatasetOGCIndexView",
    "DatasetOGCRecordsIndexView",
    "OGCRecordsCollectionView",
    "OGCRecordsCollectionDetailView",
    "DocsIndexView",
    "oauth2_redirect",
    "viewset_factory",
)
