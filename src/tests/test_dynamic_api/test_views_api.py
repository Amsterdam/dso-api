import inspect
import json
import math
from unittest import mock

import orjson
import pytest
from django.contrib.gis.geos import Point
from django.db import connection
from django.urls import reverse
from rest_framework.response import Response
from schematools.contrib.django import models
from schematools.contrib.django.db import create_tables

from dso_api.dynamic_api.permissions import fetch_scopes_for_dataset_table, fetch_scopes_for_model
from rest_framework_dso.crs import CRS, RD_NEW
from rest_framework_dso.response import StreamingResponse


class AproxFloat(float):
    def __eq__(self, other):
        # allow minor differences in comparing the floats. This makes sure that the
        # precise float deserialization of orjson.loads() doesn't cause any
        # comparison issues. The first 14 decimals must be the same:
        return math.isclose(self, other, rel_tol=1e-14, abs_tol=1e-14)


GEOJSON_POINT = [
    AproxFloat(c) for c in Point(10, 10, srid=RD_NEW.srid).transform("EPSG:4326", clone=True)
]


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
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"
    assert response["X-Pagination-Count"] == "1"
    assert response["X-Total-Count"] == "0"


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

    def test_response_has_crs_from_accept_crs_empty_data(self, api_client, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_content(self, api_client, filled_router, afval_container):
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
        through querying with the right mandatoryFilterSets
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
                            "parkeervakken": {"mandatoryFilterSets": [["regimes.aantal[gte]"]]}
                        }
                    }
                }
            },
        )

        models.DatasetTable.objects.filter(name="parkeervakken").update(auth="DATASET/SCOPE")
        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        assert api_client.get(base_url).status_code == 403
        assert api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 403
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
        assert api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
        token = fetch_auth_token(["DATASET/SCOPE"])
        assert api_client.get(base_url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
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
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that a single profile is activated
        assert parkeervak_data["type"] == parkeervak.type
        assert parkeervak_data["soort"] == parkeervak.soort[:1]
        # assert that there is no table scope
        assert "id" not in parkeervak_data.keys()
        # 2) profile and dataset scope
        token = fetch_auth_token(["PROFIEL/SCOPE", "DATASET/SCOPE"])
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        parkeervak_data = response.data["_embedded"]["parkeervakken"][0]
        # assert that dataset scope permissions overrules lower profile permission
        assert parkeervak_data["soort"] == parkeervak.soort
        assert "id" in parkeervak_data.keys()
        # 3) two profile scopes
        token = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        # trigger one profile
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
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

    def test_auth_on_table_schema_protects(self, api_client, filled_router, afval_schema):
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
            [field_name for field_name in response.data["_embedded"]["containers"][0].keys()]
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
            [field_name for field_name in response.data["_embedded"]["containers"][0].keys()]
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
            [field_name for field_name in response.data["_embedded"]["containers"][0].keys()]
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

        assert "dagen" in response.data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()

        public_response = api_client.get(url)

        assert (
            "dagen"
            not in public_response.data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()
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

    def test_auth_on_dataset_detail_has_profile_field_permission(
        self,
        api_client,
        filled_router,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
    ):
        """Prove that having no scope on the dataset, but a
        mandatory query on ['id'] gives access to its detailview.
        """
        parkeervakken_parkeervak_model.objects.create(id="121138489047")
        models.Dataset.objects.filter(name="parkeervakken").update(auth="DATASET/SCOPE")
        models.Profile.objects.create(
            name="mag_niet",
            scopes=["MAY/NOT"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {"mandatoryFilterSets": [["buurtcode", "type"]]}
                        }
                    }
                }
            },
        )
        models.Profile.objects.create(
            name="mag_wel",
            scopes=["MAY/ENTER"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {
                                "mandatoryFilterSets": [["buurtcode", "type"], ["id"]]
                            }
                        }
                    }
                }
            },
        )
        models.Profile.objects.create(
            name="alleen_volgnummer",
            scopes=["ONLY/VOLGNUMMER"],
            schema_data={
                "datasets": {
                    "parkeervakken": {
                        "tables": {
                            "parkeervakken": {"mandatoryFilterSets": [["id", "volgnummer"]]}
                        }
                    }
                }
            },
        )
        detail = reverse("dynamic_api:parkeervakken-parkeervakken-detail", args=["121138489047"])
        detail_met_volgnummer = detail + "?volgnummer=3"
        may_not = fetch_auth_token(["MAY/NOT"])
        may_enter = fetch_auth_token(["MAY/ENTER"])
        dataset_scope = fetch_auth_token(["DATASET/SCOPE"])
        profiel_met_volgnummer = fetch_auth_token(["ONLY/VOLGNUMMER"])
        response = api_client.get(detail, HTTP_AUTHORIZATION=f"Bearer {may_not}")
        assert response.status_code == 403, response.data
        response = api_client.get(detail, HTTP_AUTHORIZATION=f"Bearer {may_enter}")
        assert response.status_code == 200, response.data
        response = api_client.get(detail_met_volgnummer, HTTP_AUTHORIZATION=f"Bearer {may_enter}")
        assert response.status_code == 200, response.data
        response = api_client.get(detail, HTTP_AUTHORIZATION=f"Bearer {dataset_scope}")
        assert response.status_code == 200, response.data
        response = api_client.get(detail, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}")
        assert response.status_code == 403, response.data
        response = api_client.get(
            detail_met_volgnummer, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}"
        )
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

        url = reverse("dynamic_api:gebieden-ggwgebieden-detail", args=["03630950000000.1"])
        url = f"{url}?_expand=true"
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data["_embedded"]["bestaatUitBuurten"]["id"] == "03630000000078.1"

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
        assert dict(response.data["_embedded"]["bestaatUitBuurten"][0]) == {
            "_links": {
                "bestaatUitBuurtenGgwgebieden": [
                    {
                        "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000/?volgnummer=1",  # noqa: E501
                        "title": "03630950000000.1",
                    }
                ],
                "buurtenWoningbouwplan": [],
                "ligtInWijk": None,
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#buurten",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                    "title": "03630000000078.1",
                },
            },
            "geometrie": None,
            "ligtInWijkVolgnummer": None,
            "ligtInWijkIdentificatie": None,
            "volgnummer": 1,
            "naam": None,
            "code": None,
            "identificatie": "03630000000078",
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "id": "03630000000078.1",
        }
        assert dict(response.data["_embedded"]["ggwgebieden"][0]) == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#ggwgebieden",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000/?volgnummer=1",  # noqa: E501
                    "title": "03630950000000.1",
                },
                "bestaatUitBuurten": [
                    {
                        "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",  # noqa: E501
                        "title": "03630000000078.1",
                    },
                ],
            },
            "geometrie": None,
            "volgnummer": 1,
            "identificatie": "03630950000000",
            "id": "03630950000000.1",
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "naam": None,
            "registratiedatum": None,
        }

    def test_detail_no_expand_for_loose_relation(
        self,
        api_client,
        reloadrouter,
        statistieken_model,
        buurten_model,
        statistieken_data,
        buurten_data,
    ):
        """Without _expand=true there is no _embedded field.
        The buurt link must appear in the _links field inside an HAL envelope.
        The buurt link is not resolved to the latest volgnummer.
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.data == {
            "_links": {
                "buurt": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/",
                    "title": "03630000000078",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/meldingen#statistieken",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1/",
                    "title": "1",
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
        }

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
        assert response.data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/meldingen#statistieken",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1/",
                    "title": "1",
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
            "_embedded": {
                "buurt": {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#buurten",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2",  # noqa: E501
                            "title": "03630000000078.2",
                        },
                    },
                    "code": None,
                    "naam": None,
                    "geometrie": None,
                    "ligtInWijkVolgnummer": None,
                    "ligtInWijkIdentificatie": None,
                    "volgnummer": 2,
                    "identificatie": "03630000000078",
                    "eindGeldigheid": None,
                    "beginGeldigheid": None,
                    "id": "03630000000078.2",
                }
            },
        }

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
        assert (
            response.data["_embedded"]["buurt"][0]["_links"]["self"]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2"
        )
        assert response.data["_embedded"]["statistieken"][0]["id"] == 1
        assert (
            response.data["_embedded"]["statistieken"][0]["_links"]["buurt"]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/"
        )
        assert "_embedded" not in response.data["_embedded"]["statistieken"][0]

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
        assert response.data["_embedded"]["woningbouwplan"][0]["_links"]["buurten"] == [
            {
                "href": "http://testserver/v1/gebieden/buurten/03630000000078/",
                "title": "03630000000078",
            }
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
        assert "buurten" not in response.data  # because it must be in  "_embedded"
        # Note that "buurten" is a ManyToMany, but upacked here because the
        # list contained only 1 item
        # (previous design choice, see EmbedHelper.get_embedded in utils.py)
        assert response.data["_embedded"]["buurten"]["id"] == "03630000000078.2"
        assert (
            response.data["_embedded"]["buurten"]["_links"]["self"]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2"
        )

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
        response = api_client.get(url)
        # check that "buurten" still contains the correct list
        assert (
            response.data["_links"]["buurten"][0]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/"
        )


@pytest.mark.django_db
class TestExportFormats:
    """Prove that other rendering formats also work as expected"""

    as_is = lambda data: data

    def test_point_wgs84(self):
        """See that our WGS84_POINT is indeed a lon/lat coordinate.
        This only compares a rounded version, as there can be subtle differences
        in the actual value depending on your GDAL/libproj version.
        """
        wgs84_point = [round(GEOJSON_POINT[0], 2), round(GEOJSON_POINT[1], 2)]
        # GeoJSON should always be longitude and latitude,
        # even though GDAL 2 vs 3 have different behavior:
        # https://gdal.org/tutorials/osr_api_tut.html#crs-and-axis-order
        assert wgs84_point == [3.31, 47.97]

    UNPAGINATED_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Geometry,Serienummer,Datumcreatie,Eigenaarnaam,Datumleegmaken\r\n"
            b"1,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "FeatureCollection",
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
                    "type": "name",
                },
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": GEOJSON_POINT,
                        },
                        "properties": {
                            "id": 1,
                            "clusterId": "c1",
                            "cluster": (
                                "http://testserver"
                                "/v1/afvalwegingen/clusters/c1/?_format=geojson"
                            ),
                            "serienummer": "foobar-123",
                            "datumCreatie": "2021-01-03",
                            "eigenaarNaam": "Dataservices",
                            "datumLeegmaken": "2021-01-03T12:13:14",
                        },
                    }
                ],
                "_links": [],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(UNPAGINATED_FORMATS.keys()))
    def test_unpaginated_list(self, format, api_client, api_rf, afval_container, filled_router):
        """Prove that the export formats generate proper data."""
        decoder, expected_type, expected_data = self.UNPAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert isinstance(response, StreamingResponse)  # still wrapped in DRF response!
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was not triggered
        assert "X-Pagination-Page" not in response
        assert "X-Pagination-Limit" not in response
        assert "X-Pagination-Count" not in response
        assert "X-Total-Count" not in response

        # proves middleware detected streaming response, and didn't break it:
        assert "Content-Length" not in response

        # Check that the response is streaming:
        assert response.streaming
        assert inspect.isgeneratorfunction(response.accepted_renderer.render)

    PAGINATED_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Geometry,Serienummer,Datumcreatie,Eigenaarnaam,Datumleegmaken\r\n"
            b"1,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n"
            b"2,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n"
            b"3,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n"
            b"4,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "FeatureCollection",
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
                    "type": "name",
                },
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": GEOJSON_POINT,
                        },
                        "properties": {
                            "id": i,
                            "clusterId": "c1",
                            "cluster": (
                                "http://testserver"
                                "/v1/afvalwegingen/clusters/c1/?_format=geojson"
                            ),
                            "serienummer": "foobar-123",
                            "datumCreatie": "2021-01-03",
                            "eigenaarNaam": "Dataservices",
                            "datumLeegmaken": "2021-01-03T12:13:14",
                        },
                    }
                    for i in range(1, 5)
                ],
                "_links": [
                    {
                        "href": (
                            "http://testserver"
                            "/v1/afvalwegingen/containers/?_format=geojson&_pageSize=4&page=2"
                        ),
                        "rel": "next",
                        "type": "application/geo+json",
                        "title": "next page",
                    }
                ],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(PAGINATED_FORMATS.keys()))
    def test_paginated_list(self, format, api_client, api_rf, afval_container, filled_router):
        """Prove that the pagination still works if explicitly requested."""
        decoder, expected_type, expected_data = self.PAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        for i in range(2, 10):
            afval_container.id = i
            afval_container.save()

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format, "_pageSize": "4"})
        assert isinstance(response, StreamingResponse)
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was triggered
        assert response["X-Pagination-Page"] == "1"
        assert response["X-Pagination-Limit"] == "4"
        assert response["X-Pagination-Count"] == "3"
        assert response["X-Total-Count"] == "9"

        # proves middleware detected streaming response, and didn't break it:
        assert "Content-Length" not in response

        # Check that the response is streaming:
        assert response.streaming
        assert inspect.isgeneratorfunction(response.accepted_renderer.render)

    EMPTY_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Geometry,Serienummer,Datumcreatie,Eigenaarnaam,Datumleegmaken\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "FeatureCollection",
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
                    "type": "name",
                },
                "features": [],
                "_links": [],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(EMPTY_FORMATS.keys()))
    def test_empty_list(self, format, api_client, api_rf, filled_router):
        """Prove that empty list pages are properly serialized."""
        decoder, expected_type, expected_data = self.EMPTY_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert isinstance(response, StreamingResponse)
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

    DETAIL_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Geometry,Serienummer,Datumcreatie,Eigenaarnaam,Datumleegmaken\r\n"
            b"1,c1,SRID=28992;POINT (10 10),foobar-123,2021-01-03,Dataservices,"
            b"2021-01-03T12:13:14\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "Feature",
                "geometry": {
                    "coordinates": GEOJSON_POINT,
                    "type": "Point",
                },
                "properties": {
                    "cluster": "http://testserver/v1/afvalwegingen/clusters/c1/?_format=geojson",
                    "clusterId": "c1",
                    "datumCreatie": "2021-01-03",
                    "datumLeegmaken": "2021-01-03T12:13:14",
                    "eigenaarNaam": "Dataservices",
                    "id": 1,
                    "serienummer": "foobar-123",
                },
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
                    "type": "name",
                },
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail(self, format, api_client, api_rf, afval_container, filled_router):
        """Prove that the detail view also returns an export of a single feature."""
        decoder, expected_type, expected_data = self.DETAIL_FORMATS[format]
        url = reverse(
            "dynamic_api:afvalwegingen-containers-detail",
            kwargs={"pk": afval_container.pk},
        )

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert isinstance(response, Response)  # still wrapped in DRF response!
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was NOT triggered
        assert "X-Pagination-Page" not in response

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail_404(self, format, api_client, api_rf, filled_router):
        """Prove that error pages are also properly rendered.
        These are not rendered in the output format, but get a generic exception.
        """
        url = reverse(
            "dynamic_api:afvalwegingen-containers-detail",
            kwargs={"pk": 9999999999},
        )

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert isinstance(response, Response)  # still wrapped in DRF response!
        assert response.status_code == 404, response.getvalue()
        assert response["Content-Type"] == "application/problem+json"
        data = json.loads(response.getvalue())
        assert data == {
            "type": "urn:apiexception:not_found",
            "title": "No containers matches the given query.",
            "detail": "Not found.",
            "status": 404,
        }

        # Paginator was NOT triggered
        assert "X-Pagination-Page" not in response
