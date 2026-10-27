import pytest


@pytest.mark.django_db
class TestDatasetOGCIndexView:
    def test_ogc_index_view(self, api_client):
        ogc_url = "/v1/ogc"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content


@pytest.mark.django_db
class TestDatasetOGCRecordsIndexView:
    def test_ogc_records_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content


@pytest.mark.django_db
class TestOGCRecordsCollectionView:
    def test_ogc_collection_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records/collections"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content


@pytest.mark.django_db
class TestOGCRecordsCollectionDetailView:
    """Prove that the OGC server logic is properly integrated in the dynamic models."""

    def test_ogc_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records/collections/afvalwegingen"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content
        assert response.data == {
            "records": [
                {
                    "id": "afvalwegingen_v1",
                    "conformsTo": [],
                    "type": "Collection",
                    "itemType": "catalog",
                    "title": "Afvalwegingen",
                    "description": "unit testing version of afvalwegingen",
                    "language": {
                        "code": "nl",
                        "name": "Dutch (Netherlands)",
                    },
                    "rights": ["OPENBAAR"],
                    "recordsArrayName": "records",
                    "links": [
                        {
                            "rel": "self",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen",
                        },
                    ],
                    "contacts": [
                        {
                            "name": "Datapunt",
                            "email": "datapunt@amsterdam.nl",
                        },
                    ],
                    "crs": [
                        "EPSG:28992",
                    ],
                    "license": "CC0 1.0",
                },
                {
                    "id": "afvalwegingen_v2",
                    "conformsTo": [],
                    "type": "Collection",
                    "itemType": "catalog",
                    "title": "Afvalwegingen",
                    "description": "unit testing version of afvalwegingen",
                    "language": {
                        "code": "nl",
                        "name": "Dutch (Netherlands)",
                    },
                    "rights": ["OPENBAAR"],
                    "recordsArrayName": "records",
                    "links": [
                        {
                            "rel": "self",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen",
                        },
                    ],
                    "contacts": [
                        {
                            "name": "Datapunt",
                            "email": "datapunt@amsterdam.nl",
                        },
                    ],
                    "crs": [
                        "EPSG:28992",
                    ],
                    "license": "CC0 1.0",
                },
            ],
        }
