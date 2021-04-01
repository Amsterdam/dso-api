import pytest
from schematools.contrib.django import models
from schematools.contrib.django.db import create_tables

from dso_api.dynamic_api.permissions import fetch_scopes_for_dataset_table, fetch_scopes_for_model
from tests.utils import read_response_xml, xml_element_to_dict


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    fetch_scopes_for_dataset_table.cache_clear()
    fetch_scopes_for_model.cache_clear()


@pytest.mark.django_db
class TestDatasetWFSView:
    """Prove that the WFS server logic is properly integrated in the dynamic models."""

    def test_wfs_view(self, api_client, afval_dataset, afval_container):
        wfs_url = (
            "/v1/wfs/afvalwegingen/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:containers"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200

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
            "/v1/wfs/parkeervakken/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=parkeervakken"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
        xml_root = read_response_xml(response)
        data = xml_element_to_dict(xml_root[0][0])

        assert "e_type" in data.keys()
        assert data == {
            "id": "1",
            "type": "Langs",
            "e_type": "E666",
            "soort": "NIET FISCA",
            "aantal": "1.0",
            "buurtcode": None,
            "geometry": None,
            "straatnaam": None,
        }

    def test_wfs_model_auth(
        self, api_client, parkeervakken_schema, parkeervakken_parkeervak_model
    ):
        models.DatasetTable.objects.filter(name="parkeervakken").update(auth="TEST/SCOPE")
        parkeervakken_parkeervak_model.objects.create(
            id=1,
            type="Langs",
            soort="NIET FISCA",
            aantal="1.0",
            e_type="E666",
        )

        wfs_url = (
            "/v1/wfs/parkeervakken/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=parkeervakken"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 403

    def test_wfs_field_auth(
        self, api_client, parkeervakken_schema, parkeervakken_parkeervak_model
    ):
        models.DatasetField.objects.filter(table__name="parkeervakken", name="e_type").update(
            auth="TEST/SCOPE"
        )
        parkeervakken_parkeervak_model.objects.create(
            id=1,
            type="Langs",
            soort="NIET FISCA",
            aantal="1.0",
            e_type="E666",
        )

        wfs_url = (
            "/v1/wfs/parkeervakken/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=parkeervakken"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
        xml_root = read_response_xml(response)
        data = xml_element_to_dict(xml_root[0][0])

        assert "e_type" not in data.keys()
        assert data == {
            "id": "1",
            "type": "Langs",
            "soort": "NIET FISCA",
            "aantal": "1.0",
            "buurtcode": None,
            "geometry": None,
            "straatnaam": None,
        }

    def test_wfs_feature_name(self, api_client, afval_dataset, afval_adresloopafstand):
        """Prove that if feature name contains non-letters like underscore,
        it can be useds find the correct table name and data
        """
        wfs_url = (
            "/v1/wfs/afvalwegingen/"
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
            f"/v1/wfs/{bommen_dataset.name}/"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=app:bommen"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        response = api_client.get(wfs_url)
        assert response.status_code == 200
        xml_root = read_response_xml(response)

        assert len(xml_root) == 0

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
