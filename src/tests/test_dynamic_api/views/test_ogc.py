import pytest


@pytest.mark.django_db
class TestOGCIndexView:
    def test_ogc_index_view(self, api_client):
        ogc_url = "/v1/ogc"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content
        assert b"/v1/ogc/records" in response.content


@pytest.mark.django_db
class TestOGCRecordsIndexView:
    def test_ogc_records_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content
        assert b"/v1/ogc/records/collections" in response.content


@pytest.mark.django_db
class TestOGCRecordsCollectionView:
    def test_ogc_collection_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records/collections"
        response = api_client.get(ogc_url)
        json = response.json()
        assert response.status_code == 200, response.content
        assert len(json["collections"]) == 1
        assert json["collections"][0]["id"] == "afvalwegingen"


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
                        {
                            "rel": "v1",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen/v1",
                        },
                        {
                            "rel": "v2",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen/v2",
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
                        {
                            "rel": "v1",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen/v1",
                        },
                        {
                            "rel": "v2",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen/v2",
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


@pytest.mark.django_db
class TestOGCRecordDetailView:
    def test_ogc_record_view(self, api_client, afval_container):
        ogc_url = "/v1/ogc/records/collections/afvalwegingen/v1"
        response = api_client.get(ogc_url)
        assert response.status_code == 200, response.content
        assert response.data == {
            "record": [
                {
                    "id": "afvalwegingen_v1",
                    "conformsTo": [],
                    "language": {"code": "nl", "name": "Dutch (Netherlands)"},
                    "links": [
                        {
                            "rel": "self",
                            "type": "application/json",
                            "href": "http://testserver/v1/ogc/records/collections/afvalwegingen/v1",
                        },
                        {
                            "rel": "WFS",
                            "type": "application/json",
                            "href": "http://testserver/v1/wfs/afvalwegingen/v1?service=WFS&request=GetCapabilities",
                        },
                    ],
                }
            ],
        }
