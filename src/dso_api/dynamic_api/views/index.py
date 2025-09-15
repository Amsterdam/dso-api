from __future__ import annotations

import logging
from collections.abc import Iterable

from django.urls import NoReverseMatch
from rest_framework.response import Response
from rest_framework.views import APIView
from schematools.contrib.django.models import Dataset

from dso_api.dynamic_api.constants import DEFAULT
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

    def _build_version_endpoints(
        self, base: str, dataset_id: str, version: str, header: str | None = None, suffix: str = ""
    ):
        raise NotImplementedError()

    def get_version_endpoints(self, ds: Dataset, base: str):
        if not ds.enable_db:
            return []
        try:
            dataset_id = ds.schema.id

            return [
                self._build_version_endpoints(
                    base, dataset_id, DEFAULT, f"Standaardversie ({ds.default_version})"
                )
            ] + [
                self._build_version_endpoints(base, dataset_id, vmajor, suffix="-version")
                for vmajor, vschema in ds.schema.versions.items()
                if vschema.status.value != "niet_beschikbaar"
            ]
        except NoReverseMatch as e:
            logger.warning("dataset %s: %s", dataset_id, e)
            return []

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
                versions = self.get_version_endpoints(ds, base)
            except NoReverseMatch as e:
                # Due to too many of these issues, avoid breaking the whole index listing for this.
                # Plus, having the front page give a 500 error is not that nice.
                logging.exception(
                    "Internal URL resolving is broken for schema {%s}: {%s}", ds.schema.id, str(e)
                )
                versions = []

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
                "versions": versions,
                "environments": [versions[0]] if versions else [],  # For catalog
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
