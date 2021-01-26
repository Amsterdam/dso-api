import pytest

from dso_api.dynamic_api.permissions import fetch_scopes_for_dataset_table, fetch_scopes_for_model


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    fetch_scopes_for_dataset_table.cache_clear()
    fetch_scopes_for_model.cache_clear()


@pytest.mark.django_db
class TestDatasetWFSView:
    """Prove that the WFS server logic is properly integrated in the dynamic models."""

    def test_wfs_view(self, api_client, filled_router):
        wfs_url = (
            "/v1/wfs/afvalwegingen/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=containers"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
