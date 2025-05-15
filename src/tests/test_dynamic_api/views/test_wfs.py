import re
import urllib.parse

import pytest
from django.urls import reverse
from schematools.contrib.django.db import create_tables

from tests.utils import read_response, read_response_xml, xml_element_to_dict


@pytest.mark.django_db
class TestDatasetWFSIndexView:
    def test_wfs_index(
        self, api_client, afval_dataset, fietspaaltjes_dataset, filled_router, drf_request
    ):
        """Prove that the WFS index view works."""
        response = api_client.get("/v1/wfs")
        assert response.status_code == 200

        # Prove that response contains the correct data
        base = drf_request.build_absolute_uri("/").rstrip("/")
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
                            "api_url": f"{base}/v1/wfs/afvalwegingen",
                            "specification_url": (
                                f"{base}/v1/wfs/afvalwegingen?SERVICE=WFS&REQUEST=GetCapabilities"
                            ),
                            "documentation_url": f"{base}/v1/wfs/afvalwegingen",
                        }
                    ],
                    "related_apis": [
                        {"type": "rest_json", "url": f"{base}/v1/afvalwegingen"},
                        {"type": "MVT", "url": f"{base}/v1/mvt/afvalwegingen"},
                    ],
                    "api_authentication": ["OPENBAAR"],
                    "api_type": "WFS",
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
                            "api_url": f"{base}/v1/wfs/fietspaaltjes",
                            "specification_url": (
                                f"{base}/v1/wfs/fietspaaltjes?SERVICE=WFS&REQUEST=GetCapabilities"
                            ),
                            "documentation_url": f"{base}/v1/wfs/fietspaaltjes",
                        }
                    ],
                    "related_apis": [
                        {"type": "rest_json", "url": f"{base}/v1/fietspaaltjes"},
                        {"type": "MVT", "url": f"{base}/v1/mvt/fietspaaltjes"},
                    ],
                    "api_authentication": ["OPENBAAR"],
                    "api_type": "WFS",
                    "organization_name": "Gemeente Amsterdam",
                    "organization_oin": "00000001002564440000",
                    "contact": {
                        "email": "datapunt@amsterdam.nl",
                        "url": "https://github.com/Amsterdam/dso-api/issues",
                    },
                },
            }
        }

    def test_wfs_index_disabled(
        self, api_client, disabled_afval_dataset, fietspaaltjes_dataset, filled_router
    ):
        """Prove that disabled API's are not listed."""
        response = api_client.get("/v1/wfs")
        assert response.status_code == 200
        assert set(response.data["datasets"].keys()) == {"fietspaaltjes"}


@pytest.mark.django_db
class TestDatasetWFSView:
    """Prove that the WFS server logic is properly integrated in the dynamic models."""

    def test_html_view(self, client, filled_router, fietspaaltjes_dataset):
        """Assert that fietspaaltjes has WFS docs."""
        fietspaaltjes_doc = reverse("dynamic_api:wfs", kwargs={"dataset_name": "fietspaaltjes"})
        assert fietspaaltjes_doc

        response = client.get(fietspaaltjes_doc, headers={"Accept": "text/html"})
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Check for the CSV and GeoJSON download links.
        assert "<h2>" in content
        assert re.search(r'href=".*OUTPUTFORMAT=CSV">', content, re.I)
        assert re.search(r'href=".*OUTPUTFORMAT=geojson">', content, re.I)

    def test_wfs_view(self, api_client, afval_dataset, afval_container):
        wfs_url = (
            "/v1/wfs/afvalwegingen"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:containers"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200, response.content

    def test_wfs_view_disabled(self, api_client, disabled_afval_dataset, afval_container):
        wfs_url = (
            "/v1/wfs/afvalwegingen"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:containers"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 404

    def test_wfs_field_public(
        self, api_client, parkeervakken_schema, parkeervakken_parkeervak_model
    ):
        parkeervakken_parkeervak_model.objects.create(
            id=1,
            type="Langs",
            soort="NIET FISCA",
            aantal="1.0",
            e_type="E666",
        )

        wfs_url = (
            "/v1/wfs/parkeervakken"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=parkeervakken"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200, response.content
        xml_root = read_response_xml(response)
        data = xml_element_to_dict(xml_root[0][0])

        assert "e_type" in data
        assert data == {
            "id": "1",
            "type": "Langs",
            "e_type": "E666",
            "soort": "NIET FISCA",
            "aantal": "1.0",
            "buurtcode": None,
            "geometry": None,
            "straatnaam": None,
            "volgnummer": None,
        }

    def test_wfs_feature_name(self, api_client, afval_dataset, afval_adresloopafstand):
        """Prove that if feature name contains non-letters like underscore,
        it can be useds find the correct table name and data
        """
        wfs_url = (
            "/v1/wfs/afvalwegingen"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:adres_loopafstand"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
        xml_root = read_response_xml(response)
        data = xml_element_to_dict(xml_root[0][0])
        assert data == {
            "name": "999",
            "id": "999",
            "geometry": None,
            "serienummer": "foobar-456",
        }

    def test_wfs_default_dataset_exposed(
        self,
        api_client,
        router,
        bommen_dataset,
    ):
        """Prove that if feature name contains non-letters like underscore,
        it can be useds find the correct table name and data
        """
        router.reload()
        # manually creating tables, as we do not want to use `filled_router` here.
        create_tables(bommen_dataset)
        wfs_url = (
            f"/v1/wfs/{bommen_dataset.name}"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:bommen"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
        xml_root = read_response_xml(response)

        assert len(xml_root) == 0

    @pytest.mark.skip(
        reason="Test was designed for old implementation of versioned datasets."
        "Will need to be re-implemented once versioning is in place."
    )
    def test_wfs_non_default_dataset_not_exposed(
        self,
        api_client,
        router,
        bommen_v2_dataset,
    ):
        """Prove that if feature name contains non-letters like underscore,
        it can be useds find the correct table name and data
        """
        router.reload()
        # manually creating tables.
        # Not using filled_router here, as it will throw RuntimeError,
        #  due to missing model, which is expected,
        #  because non-default dataset is not expected to be registered in router.
        create_tables(bommen_v2_dataset)

        wfs_url = (
            f"/v1/wfs/{bommen_v2_dataset.name}/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:bommen"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestDatasetWFSViewAuth:
    @staticmethod
    def request(client, fetch_auth_token, dataset: str, scopes: list[str]) -> str:
        url = (
            f"/v1/wfs/{dataset}"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=things"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        token = fetch_auth_token(scopes)
        return client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    @staticmethod
    def parse_response(response) -> dict:
        xml_root = read_response_xml(response)
        return xml_element_to_dict(xml_root[0][0])

    def test_wfs_model_unauthorized(
        self, api_client, geometry_authdataset_thing, fetch_auth_token, filled_router
    ):
        # We need TEST/TOP.
        response = self.request(api_client, fetch_auth_token, "geometry_authdataset", [])
        assert response.status_code == 403

    def test_wfs_model_unauthorized_index_page_works(
        self, api_client, geometry_authdataset_thing, filled_router
    ):
        response = api_client.get("/v1/wfs/geometry_authdataset")
        assert response.status_code == 200
        content = str(response.content)
        for field in ["id", "metadata", "geometry"]:
            # all fields should be available on the index page, even though auth is present
            assert f"<th><code>{field}</code></th>" in content

    def test_wfs_model_authorized(
        self, api_client, geometry_authdataset_thing, fetch_auth_token, filled_router
    ):
        response = self.request(api_client, fetch_auth_token, "geometry_authdataset", ["TEST/TOP"])
        assert response.status_code == 200

        # We should get a full result, regardless of "auth" on properties,
        # if we have access to the dataset.
        data = self.parse_response(response)
        assert data == {
            "boundedBy": {"Envelope": [{"lowerCorner": "10 10"}, {"upperCorner": "10 10"}]},
            "geometry": {"Point": {"pos": "10 10"}},
            "id": "1",
            "metadata": "secret",
        }

    def test_wfs_field_auth(
        self, api_client, geometry_auth_thing, fetch_auth_token, filled_router
    ):
        response = self.request(api_client, fetch_auth_token, "geometry_auth", ["TEST/GEO"])
        assert response.status_code == 200
        data = self.parse_response(response)
        assert data == {
            "boundedBy": {"Envelope": [{"lowerCorner": "10 10"}, {"upperCorner": "10 10"}]},
            "id": "1",
            "geometry_with_auth": {"Point": {"pos": "10 10"}},
        }

    @pytest.mark.parametrize("scopes", [[], ["TEST/META"]])
    def test_wfs_field_auth_invalid(
        self, api_client, geometry_auth_thing, fetch_auth_token, filled_router, scopes
    ):
        """When there is no access to the geometry field, the whole feature can't be accessed."""
        response = self.request(api_client, fetch_auth_token, "geometry_auth", scopes)
        assert response.status_code == 403, read_response(response)

    def test_wfs_filter_auth(
        self,
        api_client,
        geometry_auth_thing,
        fetch_auth_token,
        filled_router,
    ):
        """WFS should not allow filtering on fields with "auth" without the proper scopes.

        Otherwise, it would allow indirect access (esp. through wildcard filters).
        """
        filter = urllib.parse.urlencode(
            {
                "FILTER": """
                  <Filter>
                    <PropertyIsEqualTo>
                      <ValueReference>metadata</ValueReference>
                      <Literal>secret</Literal>
                    </PropertyIsEqualTo>
                  </Filter>"""
            }
        )
        url = (
            "/v1/wfs/geometry_auth"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=things"
            f"&OUTPUTFORMAT=application/gml+xml&{filter}"
        )

        # The AuthenticatedFeatureType will deny access because no geometry field is readable.
        response = api_client.get(url)
        assert response.status_code == 403, response
        root = read_response_xml(response)
        assert root[0].attrib == {"exceptionCode": "PermissionDenied", "locator": "typeNames"}
        assert root[0][0].text == (
            "You do not have permission to perform this action, "
            "because you don't have permission to access the geometry element."
        )

        # With the proper scopes, we should get a result, but still can't filter on unauth fields.
        token = fetch_auth_token(["TEST/GEO"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 400, response
        root = read_response_xml(response)
        assert root[0].attrib == {"exceptionCode": "InvalidParameterValue", "locator": "filter"}
        assert root[0][0].text == "Field 'metadata' does not exist."

        # With the proper scopes, we should get a result.
        token = fetch_auth_token(["TEST/GEO", "TEST/META"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response
        data = self.parse_response(response)
        assert data == {
            "boundedBy": {"Envelope": [{"lowerCorner": "10 10"}, {"upperCorner": "10 10"}]},
            "geometry_with_auth": {"Point": {"pos": "10 10"}},
            "id": "1",
            "metadata": "secret",
        }

    def test_wfs_model_multiple_geometries(
        self, api_client, geometry_multiple_thing, fetch_auth_token, filled_router
    ):
        """
        When having multiple geometries, expect the main geometry to be accessible by default.
        This test will validate that the mainGeometry is added first.
        """
        response = self.request(api_client, fetch_auth_token, "geometry_multiple", [])
        assert response.status_code == 200

        # Expect other geometrie to be available as well
        wfs_url = (
            "/v1/wfs/geometry_multiple"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=things-geometrie"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
