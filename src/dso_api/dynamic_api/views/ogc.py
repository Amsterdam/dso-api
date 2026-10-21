"""The WFS views expose all geographic datasets as WFS endpoints and feature types.

The main logic of the WFS server can be found in the `django-gisserver`_
package. By overriding it's :class:`~gisserver.views.WFSView` class,
our dynamic models can be introduced into the `django-gisserver`_ logic.
Specifically, the following happens:

* The ``FeatureType`` class is overwritten to implement permission checks.
* The ``WFSView.get_feature_types()`` dynamically returns the feature types
  based on the datasets.
* The query parameters ``?expand`` and ``?embed`` extend the server logic
  to provide object-embedding at the feature type level.

The WFS server itself doesn't have any awareness of Amsterdam Schema, or the
fact that model definitions are dynamically generated. It's output and filter
logic is purely based on the provided ``FeatureType`` definition. Hence, the
server can act differently based on authorization logic - as we provide a
different ``FeatureType`` definition in such case.

By making the dataset name part of the view ``kwargs``,
each individual dataset becomes a separate WFS server endpoint.
The models of that dataset become WFS feature types.

.. _django-gisserver: https://github.com/Amsterdam/django-gisserver
"""

import logging

from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from dso_api.dynamic_api.datasets import get_active_datasets

from .index import APIIndexView

logger = logging.getLogger(__name__)


# deze met TemplateView instead?
class DatasetOGCIndexView(APIIndexView):
    """Overview of available OGC endpoints."""

    template_name = "ogc/index.html"
    name = "OGC endpoints"  # for browsable API.
    description = (
        "Alle OGC endpoints voor de gegevens in de DSO-API.\n\n"
        "Voor het gebruik van OGC endpoints, zie: "
        "[Datasets laden in GIS-pakketten](/v1/docs/generic/gis.html),"
        " en de algemene [documentatie van de DSO-API](/v1/docs/)."
    )
    api_type = "OGC"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["records_url"] = reverse("ogc-records-index")
        context["features_url"] = reverse("ogc-features-index")
        context["collections_url"] = reverse("ogc-records-collections")
        return context


class OGCRecordsCollectionView(APIView):
    """Shows an HTML page with an overview of record collections."""

    template_name = "dso_api/dynamic_api/ogc_dataset.html"
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
    """An OGC view for a single dataset."""

    template_name = "dso_api/dynamic_api/ogc_dataset_detail.html"
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
            records.append(
                {
                    "id": f"{ds.schema.id}_{version}",
                    "created": "",
                    "updated": "",
                    "conformsTo": "",
                    "type": "Collection",
                    "itemType": "record",
                    "title": ds.schema.title or ds.schema.name,
                    "description": ds.schema.description or "",
                    "extent": "",
                    "crs": "",
                    "keywords": "",
                    "language": "nl",
                    "languages": [],
                    "resourceLanguages": ["nl"],
                    "contacts": "datapunt@amsterdam.nl",
                    "rights": list(ds.schema.auth) or None,
                    "recordsArrayName": "records",
                    "links": [
                        {
                            "rel": "self",
                            "type": "application/json",
                            "href": collection_url,
                        },
                    ],
                }
            )

            if ds.schema.license:
                records.append({"license": ds.schema.license})

            if ds.schema.get("theme"):
                records.append({"themes": ds.schema.get("theme")})

        return Response({"records": records})
