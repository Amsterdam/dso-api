import logging

from django.views.generic import TemplateView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from dso_api.dynamic_api.datasets import get_active_datasets

logger = logging.getLogger(__name__)


class DatasetOGCIndexView(TemplateView):
    """Overview of available OGC endpoints."""

    template_name = "dso_api/dynamic_api/ogc_dataset.html"
    name = "OGC endpoints"
    api_type = "OGC"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        base = self.request.build_absolute_uri("/").rstrip("/")
        context["records_url"] = f"{base}/v1/ogc/records"
        context["features_url"] = f"{base}/v1/ogc/features"

        return context


class DatasetOGCRecordsIndexView(TemplateView):
    """Overview of OGC Records endpoints."""

    template_name = "dso_api/dynamic_api/ogc_records.html"
    name = "OGC records"
    api_type = "OGC"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        base = self.request.build_absolute_uri("/").rstrip("/")
        context["collection_url"] = f"{base}/v1/ogc/records/collections"

        return context


class OGCRecordsCollectionView(APIView):
    """Shows a JSON page with an overview of record collections."""

    renderer_classes = [JSONRenderer]
    name = "Record Collections"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def get(self, request, *args, **kwargs):
        base = request.build_absolute_uri("/").rstrip("/")
        datasets = self.get_datasets()

        collections = []

        for dataset in datasets:
            collections.append(
                {
                    "id": str(dataset.schema.id),
                    "title": dataset.schema.title or dataset.name,
                    "description": dataset.schema.description or "",
                    "links": [
                        {
                            "rel": "self",
                            "type": "application/json",
                            "href": (f"{base}/v1/ogc/records/collections/{dataset.path}"),
                        }
                    ],
                }
            )

        return Response({"collections": collections})


class OGCRecordsCollectionDetailView(APIView):
    """An JSON page for a single OGC record collection (dataset)."""

    renderer_classes = [JSONRenderer]
    name = "Records"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def get(self, request, *args, **kwargs):
        base = request.build_absolute_uri("/").rstrip("/")
        datasets = self.get_datasets()
        dataset_name = self.kwargs.get("dataset_name")
        collection_url = f"{base}/v1/ogc/records/collections/{dataset_name}"
        records = []

        ds = next(
            (dataset for dataset in datasets if str(dataset.schema.id) == str(dataset_name)),
            None,
        )

        for version, _ in ds.schema.versions.items():
            records.extend(
                self.build_record_collection(
                    ds=ds,
                    version=version,
                    collection_url=collection_url,
                )
            )

        return Response({"records": records})

    def build_record_collection(self, ds, version, collection_url):
        """Handle missing attributes and ensure each OGC field has the expected datatype."""
        metadata = {
            "id": f"{ds.schema.id}_{version}",
            "conformsTo": [],
            "type": "Collection",
            "itemType": "catalog",
            "title": ds.schema.title or ds.schema.name,
            "description": ds.schema.description or "",
            "language": {"code": "nl", "name": "Dutch (Netherlands)"},
            "rights": list(ds.schema.auth),
            "recordsArrayName": "records",
            "links": [
                {
                    "rel": "self",
                    "type": "application/json",
                    "href": collection_url,
                },
            ],
        }

        if ds.schema.get("dateCreated"):
            metadata["created"] = ds.schema.get("dateCreated")

        if ds.schema.get("contactPoint"):
            metadata["contacts"] = list(ds.schema.contactPoint)
        else:
            metadata["contacts"] = [{"name": "Datapunt", "email": "datapunt@amsterdam.nl"}]

        if ds.schema.get("crs"):
            metadata["crs"] = [ds.schema.get("crs")]

        if ds.schema.get("theme"):
            metadata["themes"] = [{"concepts": ds.schema.get("theme")}]

        if ds.schema.get("keywords"):
            metadata["keywords"] = list(ds.schema.get("keywords"))

        if ds.schema.get("license"):
            metadata["license"] = ds.schema.license

        return [metadata]
