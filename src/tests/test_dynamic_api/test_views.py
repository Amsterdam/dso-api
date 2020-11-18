import json
import pytest
from unittest import mock
from django.db import connection
from django.urls import reverse

from rest_framework_dso.crs import CRS, RD_NEW
from schematools.contrib.django import models
from schematools.contrib.django.db import create_tables
from dso_api.dynamic_api.permissions import (
    fetch_scopes_for_dataset_table,
    fetch_scopes_for_model,
)


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    fetch_scopes_for_dataset_table.cache_clear()
    fetch_scopes_for_model.cache_clear()


@pytest.mark.django_db
def test_list_dynamic_view(api_client, api_rf, router, bommen_dataset):
    """Prove that building the router also creates the available viewsets."""
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 1

    # Make sure the tables are created too
    if "bommen_bommen" not in connection.introspection.table_names():
        create_tables(bommen_dataset.schema)

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:bommen-bommen-list")

    # Prove that the view is available and works
    response = api_client.get(url)
    assert response.status_code == 200, response.data
    assert response.json() == {
        "_links": {
            "self": {"href": "http://testserver/v1/bommen/bommen/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "_embedded": {"bommen": []},
        "page": {"number": 1, "size": 20, "totalElements": 0, "totalPages": 1},
    }


@pytest.mark.django_db
def test_filled_router(api_client, filled_router):
    """Prove that building the router also creates the available viewsets."""
    url = reverse("dynamic_api:bommen-bommen-list")
    response = api_client.get(url)
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_list_dynamic_view_unregister(api_client, api_rf, filled_router):
    """Prove that unregistering"""
    url = reverse("dynamic_api:bommen-bommen-list")
    viewset = filled_router.registry[0][1]

    # Normal requests give a 200
    response = api_client.get(url)
    assert response.status_code == 200

    # Prove that unloading the model also removes the API from urls.py
    filled_router.clear_urls()
    response = api_client.get(url)
    assert response.status_code == 404

    # Prove that if any requests to the viewset were still pending,
    # they also return a 404 now. This means they passed the URL resolving,
    # but were paused during the read-lock.
    request = api_rf.get(url)
    view = viewset.as_view({"get": "list"})
    response = view(request)
    assert response.status_code == 404, response.data


@pytest.mark.django_db
class TestDSOViewMixin:
    """Prove that the DSO view mixin logic is used within the dynamic API."""

    def test_not_supported_crs(self, api_client, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:2000")
        assert response.status_code == 406, response.data

    def test_bogus_crs(self, api_client, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="nonsense")
        assert response.status_code == 406, response.data

    def test_response_has_crs_from_accept_crs(self, api_client, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_accept_crs_empty_data(
        self, api_client, filled_router
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_content(
        self, api_client, filled_router, afval_container
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert RD_NEW == CRS.from_string(response["Content-Crs"])


# TODO: Make parametrized, too much repetion. JJM
@pytest.mark.django_db
class TestAuth:
    """ Test authorization """

    def test_mandatory_filters(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
    ):
        """
        Tests that profile permissions with are activated
        through querying with of the mandatoryFilterSets
        """
        from dso_api.dynamic_api.urls import router

        router.reload()
        # need to reload router, regimes is a nested table
        # and router will not know of it's existence
        models.Profile.objects.create(
            name="parkeerwacht",
            scopes=["PROFIEL/SCOPE"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [
                                    ["buurtcode", "type"],
                                    ["regimes.inWerkingOp"],
                                ]
                            }
                        }
                    }
                }
            },
        )
        models.Profile.objects.create(
            name="parkeerwacht",
            scopes=["PROFIEL2/SCOPE"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [["regimes.aantal[gte]"]]
                            }
                        }
                    }
                }
            },
        )

        models.DatasetTable.objects.filter(name="parkeervakken").update(
            auth="DATASET/SCOPE"
        )
        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        assert api_client.get(base_url).status_code == 403
        assert (
            api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code
            == 403
        )
        assert (
            api_client.get(
                f"{base_url}?buurtcode=A05d", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code
            == 403
        )
        assert (
            api_client.get(
                f"{base_url}?buurtcode=A05d&type=E9",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            ).status_code
            == 200
        )
        assert (
            api_client.get(
                f"{base_url}?regimes.inWerkingOp=20:05",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            ).status_code
            == 200
        )
        assert (
            api_client.get(
                f"{base_url}?regimes.inWerkingOp=", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code
            == 403
        )
        assert (
            api_client.get(
                f"{base_url}?regimes.inWerkingOp", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code
            == 403
        )

        token = fetch_auth_token(["DATASET/SCOPE", "PROFIEL/SCOPE"])
        assert (
            api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code
            == 200
        )
        token = fetch_auth_token(["DATASET/SCOPE"])
        assert (
            api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code
            == 200
        )
        token = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        assert (
            api_client.get(
                f"{base_url}?regimes.inWerkingOp=20:05",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            ).status_code
            == 200
        )
        assert (
            api_client.get(
                f"{base_url}?regimes.aantal[gte]=2",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            ).status_code
            == 200
        )

    def test_profile_field_permissions(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
    ):
        """
        Tests combination of profiles with auth scopes on dataset level.
        Profiles should be activated only when one of it's mandatoryFilterSet
        is queried. And field permissions should be inherited from dataset scope first.
        """
        from dso_api.dynamic_api.urls import router

        router.reload()
        models.Profile.objects.create(
            name="parkeerwacht",
            scopes=["PROFIEL/SCOPE"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [
                                    ["id"],
                                ],
                                "fields": {"type": "read", "soort": "letters:1"},
                            }
                        }
                    }
                }
            },
        )
        models.Profile.objects.create(
            name="parkeerwacht2",
            scopes=["PROFIEL2/SCOPE"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [
                                    ["id", "type"],
                                ],
                                "fields": {"type": "letters:1", "soort": "read"},
                            }
                        }
                    }
                }
            },
        )
        models.Dataset.objects.filter(name="parkeervakken").update(auth="DATASET/SCOPE")
        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id=1,
            type="Langs",
            soort="NIET FISCA",
            aantal="1.0",
        )
        # 1) profile scope only
        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        response = api_client.get(
            f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that a single profile is activated
        assert parkeervak_data["type"] == parkeervak.type
        assert parkeervak_data["soort"] == parkeervak.soort[:1]
        # assert that there is no table scope
        assert "id" not in parkeervak_data.keys()
        # 2) profile and dataset scope
        token = fetch_auth_token(["PROFIEL/SCOPE", "DATASET/SCOPE"])
        response = api_client.get(
            f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that dataset scope permissions overrules lower profile permission
        assert parkeervak_data["soort"] == parkeervak.soort
        assert "id" in parkeervak_data.keys()
        # 3) two profile scopes
        token = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        # trigger one profile
        response = api_client.get(
            f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that only the profile is used that passed it's mandatory filterset restrictions
        assert parkeervak_data["soort"] == parkeervak.soort[:1]
        # trigger both profiles
        response = api_client.get(
            f"{base_url}?id=1&type=Langs", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that both profiles are triggered and the highest permission reigns
        assert parkeervak_data["type"] == parkeervak.type
        assert parkeervak_data["soort"] == parkeervak.soort

    def test_auth_on_dataset_schema_protects_containers(
        self, api_client, filled_router, afval_schema
    ):
        """Prove that auth protection at dataset level leads to a 403 on the container listview."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.Dataset.objects.filter(name="afvalwegingen").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_dataset_schema_protects_cluster(
        self, api_client, filled_router, afval_schema
    ):
        """Prove that auth protection at dataset level leads to a 403 on the cluster listview."""
        url = reverse("dynamic_api:afvalwegingen-clusters-list")
        models.Dataset.objects.filter(name="afvalwegingen").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_protects(
        self, api_client, filled_router, afval_schema
    ):
        """Prove that auth protection at table level (container)
        leads to a 403 on the container listview."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_does_not_protect_sibling_tables(
        self, api_client, filled_router, afval_schema, fetch_auth_token
    ):
        """Prove that auth protection at table level (cluster)
        does not protect the container list view."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="clusters").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 200, response.data

    def test_auth_on_table_schema_with_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that auth protected table (container) can be
        viewed with a token with the correct scope."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data

    def test_auth_on_table_schema_with_token_for_invalid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token
    ):
        """Prove that auth protected table (container) cannot be
        viewed with a token with an incorrect scope.
        """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        token = fetch_auth_token(["BAG/RSN"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 403, response.data

    def test_auth_on_embedded_fields_with_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that expanded fields are shown when a reference field is protected
        with an auth scope and there is a valid token"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        url = f"{url}?_expand=true"
        models.DatasetTable.objects.filter(name="clusters").update(auth="BAG/R")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data
        assert "cluster" in response.json()["_embedded"], response.data

    def test_auth_on_embedded_fields_without_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that expanded fields are *not* shown when a reference field is protected
        with an auth scope. For expand=true, we return a result,
        without the fields that are protected"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        url = f"{url}?_expand=true"
        models.DatasetTable.objects.filter(name="clusters").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert "cluster" not in response.json()["_embedded"], response.data

    def test_auth_on_specified_embedded_fields_without_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that a 403 is returned when asked for a specific expanded field that is protected
        and there is no authorization in the token for that field.
        """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        url = f"{url}?_expandScope=cluster"
        models.DatasetTable.objects.filter(name="clusters").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_individual_fields_with_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that protected fields are shown
        with an auth scope and there is a valid token"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetField.objects.filter(name="eigenaar_naam").update(auth="BAG/R")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data
        assert "eigenaarNaam" in set(
            [
                field_name
                for field_name in response.data["_embedded"]["containers"][0].keys()
            ]
        ), response.data["_embedded"]["containers"][0].keys()

    def test_auth_on_individual_fields_with_token_for_valid_scope_per_profile(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that protected fields are shown
        with an auth scope connected to Profile that gives access to specific field."""
        models.Profile.objects.create(
            name="brk_readall",
            scopes=["BRK/RSN"],
            schema_data={
                "datasets": {
                    "afvalwegingen": {
                        "tables": {"containers": {"fields": {"eigenaarNaam": "read"}}}
                    }
                }
            },
        )
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetField.objects.filter(name="eigenaar_naam").update(auth="BAG/R")
        token = fetch_auth_token(["BRK/RO", "BRK/RSN"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data
        assert "eigenaarNaam" in set(
            [
                field_name
                for field_name in response.data["_embedded"]["containers"][0].keys()
            ]
        ), response.data["_embedded"]["containers"][0].keys()

    def test_auth_on_individual_fields_without_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """Prove that protected fields are *not* shown
        with an auth scope and there is not a valid token"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetField.objects.filter(name="eigenaar_naam").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert "eigenaarNaam" not in set(
            [
                field_name
                for field_name in response.data["_embedded"]["containers"][0].keys()
            ]
        ), response.data

    def test_auth_on_field_level_is_not_cached(
        self,
        api_client,
        filled_router,
        fetch_auth_token,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
    ):
        """Prove that Auth is not cached."""
        # Router reload is needed to make sure that viewsets are using relations.
        from dso_api.dynamic_api.urls import router

        router.reload()

        url = reverse("dynamic_api:parkeervakken-parkeervakken-list")

        models.DatasetField.objects.filter(name="dagen").update(auth="BAG/R")

        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489666",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=1,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begin_tijd="00:00:00",
            eind_tijd="23:59:00",
            eind_datum=None,
            begin_datum=None,
        )

        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

        assert (
            "dagen"
            in response.data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()
        )

        public_response = api_client.get(url)

        assert (
            "dagen"
            not in public_response.data["_embedded"]["parkeervakken"][0]["regimes"][
                0
            ].keys()
        )

    def test_auth_on_dataset_protects_detail_view(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """ Prove that protection at datasets level protects detail views """
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        models.Dataset.objects.filter(name="afvalwegingen").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_datasettable_protects_detail_view(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """ Prove that protection at datasets level protects detail views """
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_dataset_detail_with_token_for_valid_scope(
        self, api_client, filled_router, afval_schema, fetch_auth_token, afval_container
    ):
        """ Prove that protection at datasets level protects detail views """
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        models.Dataset.objects.filter(name="afvalwegingen").update(auth="BAG/R")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data

    def test_auth_options_requests_are_not_protected(
        self, api_client, filled_router, afval_schema
    ):
        """Prove that options requests are not protected"""
        url = reverse("dynamic_api:afvalwegingen-clusters-list")
        models.Dataset.objects.filter(name="afvalwegingen").update(auth="BAG/R")
        response = api_client.options(url)
        assert response.status_code == 200, response.data

    def test_sort_by_accepts_camel_case(
        self, api_client, filled_router, afval_schema, afval_container
    ):
        """Prove that _sort is accepting camelCase parameters."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datumCreatie")
        assert response.status_code == 200, response.data
        assert len(response.data["_embedded"]["containers"]) == 1, response.data

    def test_sort_by_not_accepting_db_column_names(
        self, api_client, filled_router, afval_schema, afval_container
    ):
        """Prove that _sort is not accepting db column names."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datum_creatie")
        assert response.status_code == 400, response.data
        assert response.data["x-validation-errors"] == [
            "Invalid sort fields: datum_creatie"
        ], response.data

    def test_api_request_audit_logging(
        self, api_client, filled_router, afval_schema, afval_container
    ):
        """Prove that every request is logged into audit log."""

        base_url = reverse("dynamic_api:afvalwegingen-containers-list")
        url = f"{base_url}?_sort=datumCreatie"
        with mock.patch("dso_api.dynamic_api.middleware.audit_log") as log_mock:
            api_client.get(url)

        assert len(log_mock.mock_calls) == 1

        log_data = json.loads(log_mock.mock_calls[0].args[0])
        assert log_data["path"] == base_url
        assert log_data["method"] == "GET"
        assert log_data["data"] == {"_sort": "datumCreatie"}
        assert log_data["subject"] is None
        assert "request_headers" in log_data

    def test_api_authorized_request_audit_logging(
        self, api_client, filled_router, afval_schema, afval_container, fetch_auth_token
    ):
        """Prove that every authorized request is logged into audit log."""

        token = fetch_auth_token(["BAG/R"])
        base_url = reverse("dynamic_api:afvalwegingen-containers-list")
        url = f"{base_url}?_sort=datumCreatie"
        with mock.patch("dso_api.dynamic_api.middleware.audit_log") as log_mock:
            api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

        assert len(log_mock.mock_calls) == 1

        log_data = json.loads(log_mock.mock_calls[0].args[0])
        assert log_data["path"] == base_url
        assert log_data["method"] == "GET"
        assert log_data["data"] == {"_sort": "datumCreatie"}
        assert log_data["subject"] == "test@tester.nl"
        assert "request_headers" in log_data


# @pytest.mark.usefixtures("reloadrouter")
@pytest.mark.django_db
class TestEmbedTemporalTables:
    def test_detail_expand_true_for_fk_relation(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        wijken_data,
    ):
        """Prove that ligtInWijk shows up when expanded"""

        url = reverse("dynamic_api:gebieden-buurten-detail", args=["03630000000078.1"])
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data["_embedded"]["ligtInWijk"]["id"] == "03630012052035.1"

    def test_list_expand_true_for_fk_relation(
        self,
        api_client,
        reloadrouter,
        statistieken_model,
        buurten_model,
        buurten_data,
        wijken_data,
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-buurten-list")
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data["_embedded"]["ligtInWijk"][0]["id"] == "03630012052035.1"

    def test_detail_expand_true_for_nm_relation(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        ggwgebieden_model,
        ggwgebieden_data,
    ):
        """Prove that bestaatUitBuurten shows up when expanded"""

        url = reverse(
            "dynamic_api:gebieden-ggwgebieden-detail", args=["03630950000000.1"]
        )
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert (
            response.data["_embedded"]["bestaatUitBuurten"]["id"] == "03630000000078.1"
        )

    def test_list_expand_true_for_nm_relation(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        ggwgebieden_model,
        ggwgebieden_data,
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert (
            response.data["_embedded"]["bestaatUitBuurten"][0]["id"]
            == "03630000000078.1"
        )

    def test_detail_expand_true_for_loose_relation(
        self,
        api_client,
        reloadrouter,
        statistieken_model,
        buurten_model,
        statistieken_data,
        buurten_data,
    ):
        """Prove that buurt shows up when expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert (
            response.data["buurt"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/"
        )
        assert response.data["_embedded"]["buurt"]["id"] == "03630000000078.2"

    def test_list_expand_true_for_loose_relation(
        self,
        api_client,
        reloadrouter,
        statistieken_model,
        buurten_model,
        statistieken_data,
        buurten_data,
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:meldingen-statistieken-list")
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data["_embedded"]["buurt"][0]["id"] == "03630000000078.2"

    def test_list_expand_true_non_tempooral_many_to_many_to_temporal(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        woningbouwplan_model,
        woningbouwplannen_data,
    ):

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data

        #  _embedded must contain for each FK or MN relation a key (with camelCased fieldname)
        #  containing a list of all records that are being referred to
        #  for loose relations, these must be resolved to the latest 'volgnummer'
        #  _embedded must also contain a key (with table name)
        #    containing a (filtered) list of items.
        # the FK or NM relation keys in those items are urls without volgnummer

        assert response.data["_embedded"]["buurten"][0]["id"] == "03630000000078.2"
        assert response.data["_embedded"]["woningbouwplan"][0]["buurten"] == [
            "http://testserver/v1/gebieden/buurten/03630000000078/",
        ]

    def test_detail_expand_true_non_temporal_many_to_many_to_temporal(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        woningbouwplan_model,
        woningbouwplannen_data,
    ):
        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-detail", args=[1])
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data["buurten"] == [
            "http://testserver/v1/gebieden/buurten/03630000000078/",
        ]
        assert response.data["_embedded"]["buurten"]["id"] == "03630000000078.2"

    def test_independence_of_m2m_through_id_field(
        self,
        api_client,
        reloadrouter,
        buurten_model,
        buurten_data,
        woningbouwplan_model,
        woningbouwplannen_data,
    ):
        """Prove that the many-to-many relation from a non-temporal to temporal dataset
        works without using the 'id' column in the though table.
        """
        cursor = connection.cursor()
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'woningbouwplannen_woningbouwplan_buurten';
            """
        )
        column_names_before = set([column_name for (column_name,) in cursor.fetchall()])
        assert "id" in column_names_before
        """ renaming the 'id' column to 'wbw_rel_woningbouwplan_buurt_id'
        to mimick the woningbouwplannen dataset"""
        cursor.execute(
            """ALTER TABLE woningbouwplannen_woningbouwplan_buurten
            RENAME COLUMN id TO wbw_rel_woningbouwplan_buurt_id;
            """
        )
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'woningbouwplannen_woningbouwplan_buurten';
            """
        )
        column_names_after = set([column_name for (column_name,) in cursor.fetchall()])
        assert "wbw_rel_woningbouwplan_buurt_id" in column_names_after
        assert "id" not in column_names_after
        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-detail", args=[1])
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        # check that "buurten" still contains the correct list
        assert response.data["buurten"] == [
            "http://testserver/v1/gebieden/buurten/03630000000078/",
        ]
