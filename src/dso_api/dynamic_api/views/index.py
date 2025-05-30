from __future__ import annotations

import logging
from collections.abc import Iterable

from django.urls import NoReverseMatch
from rest_framework.response import Response
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset

from dso_api.dynamic_api.datasets import get_active_datasets
from rest_framework_dso.renderers import BrowsableAPIRenderer, HALJSONRenderer

logger = logging.getLogger(__name__)


class APIIndexView(APIView):
    """An overview of API endpoints for a list of Datasets,
    in a JSON format compatible with developer.overheid.nl.
    """

    schema = None  # exclude from schema

    # Restrict available formats to JSON and api
    renderer_classes = [HALJSONRenderer, BrowsableAPIRenderer]

    # For browsable API
    name = "DSO-API"
    description = ""
    response_formatter = "index_formatter"

    # Set by as_view
    api_type = "rest_json"

    def get_datasets(self) -> Iterable[Dataset]:
        return get_active_datasets().order_by("name")

    def get_environments(self, ds: Dataset, base: str) -> list[dict]:
        raise NotImplementedError()

    def get_related_apis(self, ds: Dataset, base: str) -> list[dict]:
        """Get list of other APIs exposing the same dataset"""
        raise NotImplementedError()

    def get(self, request, *args, **kwargs):
        # Data not needed for html view
        if getattr(request, "accepted_media_type", None) == "text/html":
            return Response()

        base = request.build_absolute_uri("/").rstrip("/")
        datasets = self.get_datasets()

        result = {"datasets": {}}
        for ds in datasets:
            # Don't let datasets break each other and the entire page.
            try:
                env = self.get_environments(ds, base)
                rel = self.get_related_apis(ds, base)
            except NoReverseMatch as e:
                # Due to too many of these issues, avoid breaking the whole index listing for this.
                # Plus, having the front page give a 500 error is not that nice.
                logging.exception(
                    "Internal URL resolving is broken for schema {%s}: {%s}", ds.schema.id, str(e)
                )
                env = []
                rel = []

            result["datasets"][ds.schema.id] = {
                "id": ds.schema.id,
                "short_name": ds.name,
                "service_name": ds.schema.title or ds.name,
                "status": ds.schema["status"],
                "description": ds.schema.description or "",
                "tags": ds.schema.get("theme", []),
                "terms_of_use": {
                    "government_only": "OPENBAAR" not in ds.schema.auth,
                    "pay_per_use": False,
                    "license": ds.schema.license,
                },
                "environments": env,
                "related_apis": rel,
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
