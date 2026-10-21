import pytest


@pytest.mark.django_db
class TestDatasetOGCView:
    """Prove that the OGC server logic is properly integrated in the dynamic models."""

    def test_ogc_view(self, api_client, afval_dataset, afval_container):
        ogc_url = "/v1/ogc/records/collections/afvalwegingen"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content
