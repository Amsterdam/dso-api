import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from tests.test_dynamic_api.views.test_mvt import decode_mvt
from tests.utils import patch_table_row_level_auth, read_response_xml, xml_element_to_dict


@pytest.mark.django_db
class TestRowLevelAuth:
    def test_row_level_auth_sets_fields_to_none_if_unauthorized_list_view(
        self,
        api_client,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse("dynamic_api:afvalwegingen_rla-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200
        containers = list(response.data["_embedded"]["containers"])
        for container in containers:
            for target in rla["targets"]:
                assert container[target] is None

    def test_row_level_auth_shows_fields_when_authorized_list_view(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["RLA"])}"}
        url = reverse("dynamic_api:afvalwegingen_rla-containers-list")
        response = api_client.get(url, **header)
        assert response.status_code == 200
        containers = list(response.data["_embedded"]["containers"])
        for container in containers:
            for target in rla["targets"]:
                assert container[target] is not None

    def test_row_level_auth_cannot_filter_on_target_fields_when_unauthorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse("dynamic_api:afvalwegingen_rla-containers-list")

        response = api_client.get(url, data={"eigenaarNaam": "Dataservices"})
        assert response.status_code == 403
        assert response.data["detail"] == "Cannot filter on eigenaarNaam, not authorized."

    def test_row_level_auth_can_filter_on_target_fields_when_authorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse("dynamic_api:afvalwegingen_rla-containers-list")
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["RLA"])}"}
        response = api_client.get(url, data={"eigenaarNaam": "Dataservices"}, **header)
        assert response.status_code == 200
        containers = list(response.data["_embedded"]["containers"])
        assert len(containers) == 1

    @pytest.mark.parametrize("scopes", [["BAG/R"], ["BAG/R", "RLA"]])
    def test_row_level_auth_400_if_requested_fields_doesnt_include_rla_source(
        self, api_client, fetch_auth_token, afval_schema_rla, afval_container_rla, scopes
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(scopes)}"}
        response = api_client.get(url, **header, data={"_fields": "serienummer,eigenaarNaam,id"})
        assert response.status_code == 400
        assert (
            response.data["detail"] == "Row level auth source value not found,"
            "did you forget to include this in the _fields?"
        )

    def test_row_level_auth_sets_fields_to_none_if_unauthorized_detail_view(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["BAG/R"])}"}
        response = api_client.get(url, **header)
        assert response.status_code == 200
        for target in rla["targets"]:
            assert response.data[target] is None

    def test_row_level_auth_shows_fields_when_authorized_detail_view(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["serienummer", "eigenaarNaam"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["RLA", "BAG/R"])}"}
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        response = api_client.get(url, **header)
        assert response.status_code == 200
        for target in rla["targets"]:
            assert response.data[target] is not None

    def test_row_level_auth_sets_nested_fields_to_none_if_unauthorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["eigenaarDetails.telefoonnummer", "eigenaarDetails.bsn"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["BAG/R"])}"}
        response = api_client.get(url, **header)
        assert response.status_code == 200
        assert response.data["eigenaarDetailsTelefoonnummer"] is None
        assert response.data["eigenaarDetailsBsn"] is None

    def test_row_level_auth_shows_nested_fields_when_authorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["eigenaarDetails.telefoonnummer", "eigenaarDetails.bsn"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["RLA", "BAG/R"])}"}
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        response = api_client.get(url, **header)
        assert response.status_code == 200
        assert response.data["eigenaarDetailsTelefoonnummer"] is not None
        assert response.data["eigenaarDetailsBsn"] is not None

    def test_row_level_auth_in_relations_unauthorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["geheimVeld"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "clusters",
            rla=rla,
        )
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["BAG/R"])}"}
        response = api_client.get(
            url,
            **header,
            data={
                "_expand": "true",
                "_expandScope": "cluster",
            },
        )
        assert response.status_code == 200

        embedded_cluster = response.data["_embedded"]["cluster"]

        assert embedded_cluster["geheimVeld"] is None

    def test_row_level_auth_in_relations_when_authorized(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["geheimVeld"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "clusters",
            rla=rla,
        )
        url = reverse(
            "dynamic_api:afvalwegingen_rla-containers-detail", args=[afval_container_rla.id]
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(["BAG/R", "RLA"])}"}
        response = api_client.get(
            url,
            **header,
            data={
                "_expand": "true",
                "_expandScope": "cluster",
            },
        )
        assert response.status_code == 200

        embedded_cluster = response.data["_embedded"]["cluster"]

        assert embedded_cluster["geheimVeld"] is not None

    @pytest.mark.parametrize("scopes", [[], ["RLA"]])
    def test_wfs_row_level_omits_fields_regardless_of_auth(
        self,
        api_client,
        afval_schema_rla,
        afval_container_rla,
        fetch_auth_token,
        scopes,
    ):
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["eigenaarDetails.telefoonnummer", "eigenaarDetails.bsn"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        url = (
            "/v1/wfs/afvalwegingen_rla"
            "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=containers"
            "&OUTPUTFORMAT=application/gml+xml"
        )
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(scopes)}"}
        response = api_client.get(url, **header)
        assert response.status_code == 200

        xml_root = read_response_xml(response)
        data = xml_element_to_dict(xml_root[0][0])
        # the fields from rla.targets are omitted
        assert data == {
            "boundedBy": {
                "Envelope": [{"lowerCorner": "121389 487369"}, {"upperCorner": "121389 487369"}]
            },
            "geometry": {"Point": {"pos": "121389 487369"}},
            "cluster_id": "c2",
            "id": "2",
            "datum_creatie": "2021-01-03",
            "datum_leegmaken": "2021-01-03T11:13:14+00:00",
            "eigenaar_naam": "Dataservices",
            "hide_confidential_info": "true",
            "name": "2",
            "serienummer": "foobar-234",
        }

    @pytest.mark.parametrize("scopes", [[], ["RLA"]])
    def test_mvt_content_rla(
        self,
        api_client,
        afval_schema_rla,
        afval_container_rla,
        fetch_auth_token,
        scopes,
    ):
        """Prove that the MVT view omits target fields from row level auth."""
        rla = {
            "source": "hideConfidentialInfo",
            "targets": ["eigenaarDetails.telefoonnummer", "eigenaarDetails.bsn"],
            "authMap": {"true": ["RLA"], "false": []},
        }
        patch_table_row_level_auth(
            afval_schema_rla,
            "containers",
            rla=rla,
        )
        # set geo to a point that we know is included in the tile below.
        afval_container_rla.geometry = Point(123207.6558130105, 486624.6399002579)
        afval_container_rla.save()
        url = "/v1/mvt/afvalwegingen_rla/containers/17/67327/43077.pbf"
        header = {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(scopes)}"}
        response = api_client.get(url, **header)
        # MVT view returns 204 when the tile is empty.
        assert response.status_code == 200
        assert response["Content-Type"] == "application/vnd.mapbox-vector-tile"

        vt = decode_mvt(response)

        # Tile does not contain the rla.targets
        assert vt == {
            "default": {
                "extent": 4096,
                "version": 2,
                "type": "FeatureCollection",
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [1928, 2558]},
                        "properties": {
                            "id": 2,
                            "clusterId": "c2",
                            "serienummer": "foobar-234",
                            "datumCreatie": "2021-01-03",
                            "eigenaarNaam": "Dataservices",
                            "datumLeegmaken": "2021-01-03 12:13:14+01",
                            "hideConfidentialInfo": True,
                        },
                        "id": 0,
                        "type": "Feature",
                    }
                ],
            }
        }
