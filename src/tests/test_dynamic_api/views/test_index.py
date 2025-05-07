import pytest
from django.urls import reverse
from more_ds.network.url import URL


@pytest.mark.django_db
def test_api_index_view(
    api_client, afval_dataset, fietspaaltjes_dataset, filled_router, drf_request
):
    """Prove that the API index page can be rendered."""
    url = reverse("dynamic_api:api-root")
    assert url == "/v1"

    response = api_client.get(url)
    assert response.status_code == 200, response.data

    # Prove that response contains the correct data
    BASE = URL(drf_request.build_absolute_uri("/").rstrip("/"))
    assert response.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "status": "beschikbaar",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "environments": [
                    {
                        "name": "production",
                        "api_url": BASE / "v1/afvalwegingen",
                        "specification_url": BASE / "v1/afvalwegingen",
                        "documentation_url": BASE / "v1/docs/datasets/afvalwegingen.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": BASE / "v1/wfs/afvalwegingen"},
                    {"type": "MVT", "url": BASE / "v1/mvt/afvalwegingen"},
                ],
                "api_authentication": ["OPENBAAR"],
                "api_type": "rest_json",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
            "fietspaaltjes": {
                "id": "fietspaaltjes",
                "short_name": "fietspaaltjes",
                "service_name": "fietspaaltjes",
                "status": "beschikbaar",
                "description": "",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": None,
                },
                "environments": [
                    {
                        "name": "production",
                        "api_url": BASE / "v1/fietspaaltjes",
                        "specification_url": BASE / "v1/fietspaaltjes",
                        "documentation_url": BASE / "v1/docs/datasets/fietspaaltjes.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": BASE / "v1/wfs/fietspaaltjes"},
                    {"type": "MVT", "url": BASE / "v1/mvt/fietspaaltjes"},
                ],
                "api_authentication": ["OPENBAAR"],
                "api_type": "rest_json",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
        }
    }


@pytest.mark.django_db
def test_api_index_view_disabled(
    api_client, disabled_afval_dataset, fietspaaltjes_dataset, filled_router
):
    """Prove that disabled API's are not listed."""
    response = api_client.get("/v1")
    assert response.status_code == 200, response.data
    assert set(response.data["datasets"].keys()) == {"fietspaaltjes"}


@pytest.mark.django_db
def test_api_index_subpath_view(
    api_client, afval_dataset_subpath, fietspaaltjes_dataset_subpath, filled_router, drf_request
):
    """Prove that the API sub index can be rendered.
    And only the datasets on the sub path are shown.
    """
    url_sub = reverse("dynamic_api:sub-index")
    url_subpath = reverse("dynamic_api:sub/path-index")
    assert url_sub == "/v1/sub"
    assert url_subpath == "/v1/sub/path"

    response_sub = api_client.get(url_sub)
    assert response_sub.status_code == 200, response_sub.data

    response_subpath = api_client.get(url_subpath)
    assert response_subpath.status_code == 200, response_subpath.data

    # Prove that response contains the correct data with both datasets
    BASE = URL(drf_request.build_absolute_uri("/").rstrip("/"))
    assert response_sub.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "status": "beschikbaar",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "environments": [
                    {
                        "name": "production",
                        "api_url": BASE / "v1/sub/path/afvalwegingen",
                        "specification_url": BASE / "v1/sub/path/afvalwegingen",
                        "documentation_url": BASE / "v1/docs/datasets/sub/path/afvalwegingen.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": BASE / "v1/wfs/sub/path/afvalwegingen"},
                    {"type": "MVT", "url": BASE / "v1/mvt/sub/path/afvalwegingen"},
                ],
                "api_authentication": ["OPENBAAR"],
                "api_type": "rest_json",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
            "fietspaaltjes": {
                "id": "fietspaaltjes",
                "short_name": "fietspaaltjes",
                "service_name": "fietspaaltjes",
                "status": "beschikbaar",
                "description": "",
                "tags": [],
                "terms_of_use": {"government_only": False, "pay_per_use": False, "license": None},
                "environments": [
                    {
                        "name": "production",
                        "api_url": BASE / "v1/sub/fietspaaltjes",
                        "specification_url": BASE / "v1/sub/fietspaaltjes",
                        "documentation_url": BASE / "v1/docs/datasets/sub/fietspaaltjes.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": BASE / "v1/wfs/sub/fietspaaltjes"},
                    {"type": "MVT", "url": BASE / "v1/mvt/sub/fietspaaltjes"},
                ],
                "api_authentication": ["OPENBAAR"],
                "api_type": "rest_json",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
        }
    }

    # Assert only afvalwegingen is shown on its path
    assert response_subpath.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "status": "beschikbaar",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "environments": [
                    {
                        "name": "production",
                        "api_url": BASE / "v1/sub/path/afvalwegingen",
                        "specification_url": BASE / "v1/sub/path/afvalwegingen",
                        "documentation_url": BASE / "v1/docs/datasets/sub/path/afvalwegingen.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": BASE / "v1/wfs/sub/path/afvalwegingen"},
                    {"type": "MVT", "url": BASE / "v1/mvt/sub/path/afvalwegingen"},
                ],
                "api_authentication": ["OPENBAAR"],
                "api_type": "rest_json",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
        }
    }
