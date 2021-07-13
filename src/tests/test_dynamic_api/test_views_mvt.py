import mapbox_vector_tile
import pytest

CONTENT_TYPE = "application/vnd.mapbox-vector-tile"


@pytest.mark.django_db
def test_mvt_index(api_client, afval_dataset, fietspaaltjes_dataset, filled_router, drf_request):
    """Prove that the MVT index view works."""
    response = api_client.get("/v1/mvt/")
    assert response.status_code == 200

    # Prove that response contains the correct data
    base = drf_request.build_absolute_uri("/").rstrip("/")
    assert response.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "status": "Beschikbaar",
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
                        "api_url": f"{base}/v1/mvt/afvalwegingen/",
                        "specification_url": f"{base}/v1/mvt/afvalwegingen/",
                        "documentation_url": f"{base}/v1/docs/generic/mvt.html",
                    }
                ],
                "related_apis": [
                    {"type": "rest_json", "url": f"{base}/v1/afvalwegingen/"},
                    {"type": "WFS", "url": f"{base}/v1/wfs/afvalwegingen/"},
                ],
                "api_authentication": None,
                "api_type": "MVT",
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
                        "api_url": f"{base}/v1/mvt/fietspaaltjes/",
                        "specification_url": f"{base}/v1/mvt/fietspaaltjes/",
                        "documentation_url": f"{base}/v1/docs/generic/mvt.html",
                    }
                ],
                "related_apis": [
                    {"type": "rest_json", "url": f"{base}/v1/fietspaaltjes/"},
                    {"type": "WFS", "url": f"{base}/v1/wfs/fietspaaltjes/"},
                ],
                "api_authentication": None,
                "api_type": "MVT",
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
def test_mvt_single(api_client, afval_container, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/afvalwegingen/")
    assert response.status_code == 200
    assert b"/v1/mvt/afvalwegingen/containers/{z}/{x}/{y}.pbf" in response.content


@pytest.mark.django_db
def test_mvt_content(api_client, afval_container, filled_router):
    """Prove that the MVT view produces vector tiles."""
    url = "/v1/mvt/afvalwegingen/containers/1/0/0.pbf"
    response = api_client.get(url)
    # MVT view returns 204 when the tile is empty.
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = mapbox_vector_tile.decode(response.content)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [4171, 1247]},
                    "properties": {
                        "id": 1,
                        "cluster_id": "c1",
                        "serienummer": "foobar-123",
                        "datum_creatie": "2021-01-03",
                        "eigenaar_naam": "Dataservices",
                        "datum_leegmaken": "2021-01-03 12:13:14+01",
                    },
                    "id": 0,
                    "type": 1,
                }
            ],
        }
    }


@pytest.mark.django_db
def test_mvt_forbidden(api_client, geometry_auth_thing, fetch_auth_token, filled_router):
    """Prove that an unauthorized geometry field gives 403 Forbidden"""

    # Get authorization for the meta field, but not the geometry field.
    token = fetch_auth_token(["TEST/META"])

    url = "/v1/mvt/geometry_auth/things/1/0/0.pbf"
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 403


@pytest.mark.django_db
def test_mvt_model_auth(api_client, geometry_auth_thing, fetch_auth_token, filled_router):
    """Prove that unauthorized fields are excluded from vector tiles"""

    url = "/v1/mvt/geometry_auth/things/1/0/0.pbf"
    content = {
        "default": {
            "extent": 4096,
            "version": 2,
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [4171, 1247]},
                    "id": 0,
                    "properties": {"id": 1, "metadata": "secret"},
                    "type": 1,
                }
            ],
        }
    }

    # With both required scopes, we get a full response.
    token = fetch_auth_token(["TEST/GEO", "TEST/META"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert mapbox_vector_tile.decode(response.content) == content

    # With only the GEO scope, we still get a 200 response
    # but we lose access to the metadata field.
    token = fetch_auth_token(["TEST/GEO"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200

    del content["default"]["features"][0]["properties"]["metadata"]
    assert mapbox_vector_tile.decode(response.content) == content
