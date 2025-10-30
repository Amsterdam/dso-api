import pytest
from django.urls import reverse


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
    BASE = drf_request.build_absolute_uri("/").rstrip("/")
    assert response.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "versions": [
                    {
                        "api_url": f"{BASE}/v1/afvalwegingen/v1",
                        "doc_url": f"{BASE}/v1/docs/datasets/afvalwegingen@v1.html",
                        "header": "Aanbevolen versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/afvalwegingen/v1",
                        "wfs_url": f"{BASE}/v1/wfs/afvalwegingen/v1",
                    },
                    {
                        "api_url": f"{BASE}/v1/afvalwegingen",
                        "doc_url": f"{BASE}/v1/docs/datasets/afvalwegingen.html",
                        "header": "Ongeversioneerde versie (v1)",
                        "mvt_url": f"{BASE}/v1/mvt/afvalwegingen",
                        "status": "stabiel",
                        "wfs_url": f"{BASE}/v1/wfs/afvalwegingen",
                    },
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
                "description": "",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": None,
                },
                "versions": [
                    {
                        "api_url": f"{BASE}/v1/fietspaaltjes/v1",
                        "doc_url": f"{BASE}/v1/docs/datasets/fietspaaltjes@v1.html",
                        "header": "Aanbevolen versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/fietspaaltjes/v1",
                        "wfs_url": f"{BASE}/v1/wfs/fietspaaltjes/v1",
                    },
                    {
                        "api_url": f"{BASE}/v1/fietspaaltjes",
                        "doc_url": f"{BASE}/v1/docs/datasets/fietspaaltjes.html",
                        "header": "Ongeversioneerde versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/fietspaaltjes",
                        "wfs_url": f"{BASE}/v1/wfs/fietspaaltjes",
                    },
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
def test_api_index_view_disable_api(
    api_client, disabled_afval_dataset, fietspaaltjes_dataset_disable_api, filled_router
):
    """Prove that onbeschikbare versies are not listed."""
    response = api_client.get("/v1")
    assert response.status_code == 200, response.data
    assert len(response.data["datasets"]["fietspaaltjes"]["versions"]) == 2


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
    BASE = drf_request.build_absolute_uri("/").rstrip("/")
    assert response_sub.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "versions": [
                    {
                        "api_url": f"{BASE}/v1/sub/path/afvalwegingen/v1",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/path/afvalwegingen@v1.html",
                        "header": "Aanbevolen versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/path/afvalwegingen/v1",
                        "wfs_url": f"{BASE}/v1/wfs/sub/path/afvalwegingen/v1",
                    },
                    {
                        "api_url": f"{BASE}/v1/sub/path/afvalwegingen",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/path/afvalwegingen.html",
                        "header": "Ongeversioneerde versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/path/afvalwegingen",
                        "wfs_url": f"{BASE}/v1/wfs/sub/path/afvalwegingen",
                    },
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
                "description": "",
                "tags": [],
                "terms_of_use": {"government_only": False, "pay_per_use": False, "license": None},
                "versions": [
                    {
                        "api_url": f"{BASE}/v1/sub/fietspaaltjes/v1",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/fietspaaltjes@v1.html",
                        "header": "Aanbevolen versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/fietspaaltjes/v1",
                        "wfs_url": f"{BASE}/v1/wfs/sub/fietspaaltjes/v1",
                    },
                    {
                        "api_url": f"{BASE}/v1/sub/fietspaaltjes",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/fietspaaltjes.html",
                        "header": "Ongeversioneerde versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/fietspaaltjes",
                        "wfs_url": f"{BASE}/v1/wfs/sub/fietspaaltjes",
                    },
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
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "versions": [
                    {
                        "api_url": f"{BASE}/v1/sub/path/afvalwegingen/v1",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/path/afvalwegingen@v1.html",
                        "header": "Aanbevolen versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/path/afvalwegingen/v1",
                        "wfs_url": f"{BASE}/v1/wfs/sub/path/afvalwegingen/v1",
                    },
                    {
                        "api_url": f"{BASE}/v1/sub/path/afvalwegingen",
                        "doc_url": f"{BASE}/v1/docs/datasets/sub/path/afvalwegingen.html",
                        "header": "Ongeversioneerde versie (v1)",
                        "status": "stabiel",
                        "mvt_url": f"{BASE}/v1/mvt/sub/path/afvalwegingen",
                        "wfs_url": f"{BASE}/v1/wfs/sub/path/afvalwegingen",
                    },
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
