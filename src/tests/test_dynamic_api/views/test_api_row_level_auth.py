import pytest
from django.urls import reverse

from tests.utils import patch_table_row_level_auth


@pytest.mark.django_db
class TestRowLevelAuth:
    def test_row_level_auth_sets_fields_to_none_if_unauthorized_list_view(
        self,
        api_client,
        afval_schema_rla,
        afval_container_rla,
        afval_dataset_rla,
        filled_router,
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
        afval_dataset_rla,
        filled_router,
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

    def test_row_level_auth_sets_fields_to_none_if_unauthorized_detail_view(
        self,
        api_client,
        fetch_auth_token,
        afval_schema_rla,
        afval_container_rla,
        afval_dataset_rla,
        filled_router,
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
        afval_dataset_rla,
        filled_router,
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
        afval_dataset_rla,
        filled_router,
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
        afval_dataset_rla,
        filled_router,
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
        afval_cluster_rla,
        afval_dataset_rla,
        filled_router,
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
        afval_cluster_rla,
        afval_dataset_rla,
        filled_router,
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
