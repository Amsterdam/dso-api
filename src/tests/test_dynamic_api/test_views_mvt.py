import mapbox_vector_tile
import pytest

from dso_api.dynamic_api.permissions import fetch_scopes_for_dataset_table, fetch_scopes_for_model


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    fetch_scopes_for_dataset_table.cache_clear()
    fetch_scopes_for_model.cache_clear()


CONTENT_TYPE = "application/vnd.mapbox-vector-tile"


@pytest.mark.django_db
def test_mvt_index(api_client, afval_container, filled_router):
    """Prove that the MVT index view works."""
    response = api_client.get("/v1/mvt/")
    assert response.status_code == 200
    assert b"/v1/mvt/afvalwegingen/containers/{z}/{x}/{y}.pbf" in response.content


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
