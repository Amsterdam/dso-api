from __future__ import annotations

from typing import Iterable

from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset

from dso_api.dynamic_api.datasets import get_active_datasets
from rest_framework_dso.renderers import BrowsableAPIRenderer, HALJSONRenderer


class APIIndexView(APIView):
    """An overview of API endpoints for a list of Datasets,
    in a JSON format compatible with developer.overheid.nl.
    """

    schema = None  # exclude from schema

    # Restrict available formats to JSON and api
    renderer_classes = [HALJSONRenderer, BrowsableAPIRenderer]

    # For browsable API
    name = "DSO-API"
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
    )

    # Set by as_view
    api_type = "rest_json"

    def get_datasets(self) -> Iterable[Dataset]:
        return get_active_datasets().order_by("name")

    def get_environments(self, ds: Dataset, base: str) -> list[dict]:
        return [
            {
                "name": "production",
                "api_url": base + reverse(f"dynamic_api:openapi-{ds.schema.id}"),
                "specification_url": "",
                "documentation_url": "",
            }
        ]

    def get_related_apis(self, ds: Dataset, base: str) -> list[dict]:
        """Get list of other APIs exposing the same dataset"""
        return []

    def get(self, request, *args, **kwargs):
        # Data not needed for html view
        if getattr(request, "accepted_media_type", None) == "text/html":
            return Response()

        base = request.build_absolute_uri("/").rstrip("/")
        datasets = self.get_datasets()

        result = {"datasets": {}}
        for ds in datasets:
            result["datasets"][ds.schema.id] = {
                "id": ds.schema.id,
                "short_name": ds.name,
                "service_name": ds.schema.title or ds.name,
                "status": ds.schema.get("status", "Beschikbaar"),
                "description": ds.schema.description or "",
                "tags": ds.schema.get("theme", []),
                "terms_of_use": {
                    "government_only": "auth" in ds.schema,
                    "pay_per_use": False,
                    "license": ds.schema.license,
                },
                "environments": self.get_environments(ds, base),
                "related_apis": self.get_related_apis(ds, base),
                "api_authentication": list(ds.schema.auth) or None,
                "api_type": self.api_type,
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            }

        return Response(result)
