import mapbox_vector_tile
import pytest
from schematools.contrib.django import models

from dso_api.dynamic_api.permissions import fetch_scopes_for_dataset_table, fetch_scopes_for_model


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    fetch_scopes_for_dataset_table.cache_clear()
    fetch_scopes_for_model.cache_clear()


@pytest.mark.django_db
class TestDatasetMVTView:
    """Prove that the MVT view produces vector tiles."""

    CONTENT_TYPE = "application/vnd.mapbox-vector-tile"
    URL = "/v1/mvt/afvalwegingen/containers/1/0/0.pbf"

    def test_mvt_index(self, api_client, afval_container, filled_router):
        response = api_client.get("/v1/mvt/")
        assert response.status_code == 200
        assert b"/v1/mvt/afvalwegingen/containers/{z}/{x}/{y}.pbf" in response.content

    def test_mvt_content(self, api_client, afval_container, filled_router):
        response = api_client.get(self.URL)
        assert response["Content-Type"] == self.CONTENT_TYPE
        # MVT view returns 204 when the tile is empty.
        assert response.status_code == 200

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

    def test_mvt_forbidden(self, api_client, afval_container, filled_router):
        """Prove that an unauthorized geometry field gives 403 Forbidden"""

        models.DatasetField.objects.filter(table__name="containers", name="geometry").update(
            auth="TEST/SCOPE"
        )
        response = api_client.get(self.URL)
        assert response.status_code == 403

    def test_mvt_model_auth(self, api_client, afval_container, filled_router):
        """Prove that unauthorized fields are excluded from vector tiles"""

        for name in ("datum_leegmaken", "eigenaar_naam", "serienummer"):
            models.DatasetField.objects.filter(table__name="containers", name=name).update(
                auth="TEST/SCOPE"
            )

        response = api_client.get(self.URL)
        assert response.status_code == 200

        assert mapbox_vector_tile.decode(response.content) == {
            "default": {
                "extent": 4096,
                "version": 2,
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [4171, 1247]},
                        "properties": {
                            "id": 1,
                            "cluster_id": "c1",
                            "datum_creatie": "2021-01-03",
                        },
                        "id": 0,
                        "type": 1,
                    }
                ],
            }
        }
