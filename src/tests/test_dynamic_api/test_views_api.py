import inspect
import json
import math

import orjson
import pytest
from django.apps import apps
from django.contrib.gis.geos import Point
from django.db import connection
from django.urls import NoReverseMatch, reverse
from rest_framework.response import Response
from schematools.contrib.django import models
from schematools.contrib.django.db import create_tables
from schematools.types import ProfileSchema

from rest_framework_dso.crs import CRS, RD_NEW
from rest_framework_dso.response import StreamingResponse
from tests.utils import (
    patch_dataset_auth,
    patch_field_auth,
    patch_table_auth,
    read_response,
    read_response_json,
)


class AproxFloat(float):
    def __eq__(self, other):
        # allow minor differences in comparing the floats. This makes sure that the
        # precise float deserialization of orjson.loads() doesn't cause any
        # comparison issues. The first 14 decimals must be the same:
        return math.isclose(self, other, rel_tol=1e-14, abs_tol=1e-14)


GEOJSON_POINT = [
    AproxFloat(c) for c in Point(10, 10, srid=RD_NEW.srid).transform("EPSG:4326", clone=True)
]


@pytest.mark.django_db
def test_list_dynamic_view_reload(api_client, api_rf, router, bommen_dataset):
    """Prove that building the router also creates the available viewsets."""
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:bommen-bommen-list")

    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 1

    # Make sure the tables are created too
    if "bommen_bommen" not in connection.introspection.table_names():
        create_tables(bommen_dataset, base_app_name="dso_api.dynamic_api")

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:bommen-bommen-list")

    # Prove that the view is available and works
    response = api_client.get(url)
    data = read_response_json(response)

    assert response.status_code == 200, data
    assert data == {
        "_links": {
            "self": {"href": "http://testserver/v1/bommen/bommen/"},
        },
        "_embedded": {"bommen": []},
        "page": {"number": 1, "size": 20},
    }
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"


@pytest.mark.django_db
def test_filled_router(api_client, bommen_dataset, filled_router):
    """Prove that building the router also creates the available viewsets."""
    url = reverse("dynamic_api:bommen-bommen-list")
    response = api_client.get(url)
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_list_dynamic_view_unregister(api_client, api_rf, bommen_dataset, filled_router):
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

    def test_not_supported_crs(self, api_client, afval_dataset, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:2000")
        assert response.status_code == 406, response.data

    def test_bogus_crs(self, api_client, afval_dataset, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="nonsense")
        assert response.status_code == 406, response.data

    def test_response_has_crs_from_accept_crs(self, api_client, afval_dataset, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_accept_crs_empty_data(
        self, api_client, afval_dataset, filled_router
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_content(self, api_client, afval_container, filled_router):
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
        filled_router,
    ):
        """
        Tests that profile permissions with are activated
        through querying with the right mandatoryFilterSets
        """
        patch_table_auth(parkeervakken_schema, "parkeervakken", auth=["DATASET/SCOPE"])
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "parkeerwacht",
                    "scopes": ["PROFIEL/SCOPE"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "permissions": "read",
                                    "mandatoryFilterSets": [
                                        ["buurtcode", "type"],
                                        ["regimes.inWerkingOp"],
                                    ],
                                }
                            }
                        }
                    },
                }
            )
        )
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "parkeerwacht",
                    "scopes": ["PROFIEL2/SCOPE"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "permissions": "read",
                                    "mandatoryFilterSets": [
                                        ["regimes.aantal[gte]"],
                                    ],
                                }
                            }
                        }
                    },
                }
            )
        )

        def _get(token, params=""):
            return api_client.get(f"{base_url}{params}", HTTP_AUTHORIZATION=f"Bearer {token}")

        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        assert api_client.get(base_url).status_code == 403
        assert _get(token).status_code == 403

        # See that only the proper filters activate the profile (via mandatoryFilterSets)
        assert _get(token, "?buurtcode=A05d").status_code == 403
        assert _get(token, "?buurtcode=A05d&type=E9").status_code == 200
        assert _get(token, "?regimes.inWerkingOp=20:05").status_code == 200
        assert _get(token, "?regimes.inWerkingOp=").status_code == 403
        assert _get(token, "?regimes.inWerkingOp").status_code == 403

        # See that 'auth' satisfies without needing a profile
        token2 = fetch_auth_token(["DATASET/SCOPE", "PROFIEL/SCOPE"])
        assert _get(token2).status_code == 200

        token3 = fetch_auth_token(["DATASET/SCOPE"])
        assert _get(token3).status_code == 200

        # See that both profiles can be active
        token4 = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        assert _get(token4, "?regimes.inWerkingOp=20:05").status_code == 200
        assert _get(token4, "?regimes.aantal[gte]=2").status_code == 200

    def test_profile_field_permissions(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        filled_router,
    ):
        """
        Tests combination of profiles with auth scopes on dataset level.
        Profiles should be activated only when one of it's mandatoryFilterSet
        is queried. And field permissions should be inherited from dataset scope first.
        """
        # Patch the whole dataset so related tables are also restricted
        patch_dataset_auth(parkeervakken_schema, auth=["DATASET/SCOPE"])
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "parkeerwacht",
                    "scopes": ["PROFIEL/SCOPE"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "mandatoryFilterSets": [
                                        ["id"],
                                    ],
                                    "fields": {
                                        "type": "read",
                                        "soort": "letters:1",
                                    },
                                }
                            }
                        }
                    },
                }
            )
        )
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "parkeerwacht2",
                    "scopes": ["PROFIEL2/SCOPE"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "mandatoryFilterSets": [
                                        ["id", "type"],
                                    ],
                                    "fields": {
                                        "type": "letters:1",
                                        "soort": "read",
                                    },
                                }
                            }
                        }
                    },
                }
            )
        )
        parkeervakken_parkeervak_model.objects.create(
            id=1,
            type="Langs",
            soort="NIET FISCA",
            aantal="1.0",
        )

        # 1) profile scope only
        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        parkeervak_data = data["_embedded"]["parkeervakken"][0]
        assert parkeervak_data == {
            "_links": {
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/parkeervakken/dataset#parkeervakken"
                ),
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/"},
            },
            # no ID field.
            "soort": "N",  # letters:1
            "type": "Langs",  # read permission
        }

        # 2) profile and dataset scope -> all allowed (auth of dataset is satisfied)
        token = fetch_auth_token(["PROFIEL/SCOPE", "DATASET/SCOPE"])
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        parkeervak_data = data["_embedded"]["parkeervakken"][0]
        assert parkeervak_data == {
            "_links": {
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/parkeervakken/dataset#parkeervakken"
                ),
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/"},
            },
            # Full data!
            "id": "1",
            "type": "Langs",
            "soort": "NIET FISCA",
            "aantal": 1.0,
            "eType": None,
            "geometry": None,
            "buurtcode": None,
            "straatnaam": None,
            "regimes": [],
        }

        # 3) two profile scopes, only one matches (mandatory filtersets)
        token = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        # trigger one profile
        response = api_client.get(f"{base_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        parkeervak_data = data["_embedded"]["parkeervakken"][0]
        assert parkeervak_data == {
            "_links": {
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/parkeervakken/dataset#parkeervakken"
                ),
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/"},
            },
            "soort": "N",  # letters:1
            "type": "Langs",  # read permission
        }

        # 4) both profiles + mandatory filtersets
        response = api_client.get(
            f"{base_url}?id=1&type=Langs", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        parkeervak_data = data["_embedded"]["parkeervakken"][0]
        assert parkeervak_data == {
            "_links": {
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/parkeervakken/dataset#parkeervakken"
                ),
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/"},
            },
            "type": "Langs",  # read permission
            "soort": "NIET FISCA",  # read permission
        }

    def test_auth_on_dataset_schema_protects_containers(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at dataset level leads to a 403 on the container listview."""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_dataset_schema_protects_cluster(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at dataset level leads to a 403 on the cluster listview."""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-clusters-list")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_protects(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at table level (container)
        leads to a 403 on the container listview."""
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_does_not_protect_sibling_tables(
        self, api_client, fetch_auth_token, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at table level (cluster)
        does not protect the container list view."""
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200, response.data

    def test_auth_on_table_schema_with_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that auth protected table (container) can be
        viewed with a token with the correct scope."""
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data

    def test_auth_on_table_schema_with_token_for_invalid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protected table (container) cannot be
        viewed with a token with an incorrect scope.
        """
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/RSN"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 403, response.data

    def test_auth_on_embedded_fields_with_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that expanded fields are shown when a reference field is protected
        with an auth scope and there is a valid token"""
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(
            url, data={"_expand": "true"}, HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert "cluster" in data["_embedded"], data

    def test_auth_on_embedded_fields_without_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that expanded fields are *not* shown when a reference field is protected
        with an auth scope. For expand=true, we return a result,
        without the fields that are protected"""
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert "cluster" not in data["_embedded"], data

    def test_auth_on_specified_embedded_fields_without_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that a 403 is returned when asked for a specific expanded field that is protected
        and there is no authorization in the token for that field.
        """
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, data={"_expandScope": "cluster"})
        assert response.status_code == 403, response.data

    def test_auth_on_individual_fields_with_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that protected fields are shown
        with an auth scope and there is a valid token"""
        patch_field_auth(afval_schema, "containers", "eigenaar naam", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)

        assert response.status_code == 200, data
        field_names = data["_embedded"]["containers"][0].keys()
        assert "eigenaarNaam" in field_names, field_names

    def test_auth_on_individual_fields_with_token_for_valid_scope_per_profile(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that protected fields are shown
        with an auth scope connected to Profile that gives access to specific field."""
        patch_field_auth(afval_schema, "containers", "eigenaar naam", auth=["BAG/R"])
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "brk_readall",
                    "scopes": ["BRK/RSN"],
                    "datasets": {
                        "afvalwegingen": {
                            "tables": {
                                "containers": {
                                    "fields": {
                                        "eigenaar naam": "read",
                                    }
                                }
                            }
                        }
                    },
                }
            )
        )
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BRK/RO", "BRK/RSN"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)

        assert response.status_code == 200, data
        field_names = data["_embedded"]["containers"][0].keys()
        assert "eigenaarNaam" in field_names, field_names  # profile read access

    def test_auth_on_individual_fields_without_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """Prove that protected fields are *not* shown
        with an auth scope and there is not a valid token"""
        patch_field_auth(afval_schema, "containers", "eigenaar naam", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        data = read_response_json(response)

        assert response.status_code == 200, data
        field_names = data["_embedded"]["containers"][0].keys()
        assert "eigenaarNaam" not in field_names, field_names  # profile read access

    def test_auth_on_field_level_is_not_cached(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
        filled_router,
    ):
        """Prove that Auth is not cached."""
        patch_field_auth(parkeervakken_schema, "parkeervakken", "regimes", "dagen", auth=["BAG/R"])
        url = reverse("dynamic_api:parkeervakken-parkeervakken-list")

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

        # First fetch with BAG/R token
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)

        field_names = data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()
        assert "dagen" in field_names, field_names

        # Fetch again without BAG/R token, should not return field
        public_response = api_client.get(url)
        public_data = read_response_json(public_response)
        field_names = public_data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()
        assert "dagen" not in field_names, field_names

    def test_auth_on_dataset_protects_detail_view(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """ Prove that protection at datasets level protects detail views """
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_datasettable_protects_detail_view(
        self, api_client, afval_schema, fetch_auth_token, afval_container, filled_router
    ):
        """ Prove that protection at datasets level protects detail views """
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])

        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_dataset_detail_with_token_for_valid_scope(
        self, api_client, fetch_auth_token, afval_schema, afval_container, filled_router
    ):
        """ Prove that protection at datasets level protects detail views """
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        token = fetch_auth_token(["BAG/R"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data

    def test_auth_on_dataset_detail_has_profile_field_permission(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        filled_router,
    ):
        """Prove that having no scope on the dataset, but a
        mandatory query on ['id'] gives access to its detailview.
        """
        patch_table_auth(parkeervakken_schema, "parkeervakken", auth=["DATASET/SCOPE"])
        parkeervakken_parkeervak_model.objects.create(id="121138489047")
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "mag_niet",
                    "scopes": ["MAY/NOT"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "permissions": "read",
                                    "mandatoryFilterSets": [
                                        ["buurtcode", "type"],
                                    ],
                                }
                            }
                        }
                    },
                }
            )
        )
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "mag_wel",
                    "scopes": ["MAY/ENTER"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "permissions": "read",
                                    "mandatoryFilterSets": [
                                        ["buurtcode", "type"],
                                        ["id"],
                                    ],
                                }
                            }
                        }
                    },
                }
            )
        )
        models.Profile.create_for_schema(
            ProfileSchema.from_dict(
                {
                    "name": "alleen_volgnummer",
                    "scopes": ["ONLY/VOLGNUMMER"],
                    "datasets": {
                        "parkeervakken": {
                            "tables": {
                                "parkeervakken": {
                                    "permissions": "read",
                                    "mandatoryFilterSets": [
                                        ["id", "volgnummer"],
                                    ],
                                }
                            }
                        }
                    },
                }
            )
        )

        detail_url = reverse(
            "dynamic_api:parkeervakken-parkeervakken-detail", args=["121138489047"]
        )
        detail_met_volgnummer = detail_url + "?volgnummer=3"

        may_not = fetch_auth_token(["MAY/NOT"])
        may_enter = fetch_auth_token(["MAY/ENTER"])
        dataset_scope = fetch_auth_token(["DATASET/SCOPE"])
        profiel_met_volgnummer = fetch_auth_token(["ONLY/VOLGNUMMER"])

        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {may_not}")
        assert response.status_code == 403, response.data

        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {may_enter}")
        assert response.status_code == 200, response.data

        response = api_client.get(detail_met_volgnummer, HTTP_AUTHORIZATION=f"Bearer {may_enter}")
        assert response.status_code == 200, response.data

        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {dataset_scope}")
        assert response.status_code == 200, response.data

        response = api_client.get(
            detail_url, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}"
        )
        assert response.status_code == 403, response.data

        response = api_client.get(
            detail_met_volgnummer, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}"
        )
        assert response.status_code == 200, response.data

    def test_auth_options_requests_are_not_protected(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that options requests are not protected"""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-clusters-list")
        response = api_client.options(url)
        assert response.status_code == 200, response.data

    def test_sort_by_accepts_camel_case(self, api_client, afval_container, filled_router):
        """Prove that _sort is accepting camelCase parameters."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datumCreatie")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert len(data["_embedded"]["containers"]) == 1, data

    def test_sort_by_not_accepting_db_column_names(
        self, api_client, afval_container, filled_router
    ):
        """Prove that _sort is not accepting db column names."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datum_creatie")
        data = read_response_json(response)
        assert response.status_code == 400, data
        assert data["x-validation-errors"] == ["Invalid sort fields: datum_creatie"], data

    def test_auth_on_table_schema_protects_camel_case(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at table level (adresLoopafstand)
        leads to a 403 on the adresLoopafstand listview even if table name
        is in camelCase."""
        url = reverse("dynamic_api:afvalwegingen-adres_loopafstand-list")
        table_schema = apps.get_model("afvalwegingen", "adres_loopafstand").table_schema()
        table_schema["auth"] = {"SOME_AUTH/SCOPE"}

        response = api_client.get(url)
        assert response.status_code == 403, response.data


# @pytest.mark.usefixtures("reloadrouter")
@pytest.mark.django_db
class TestEmbedTemporalTables:
    """NOTE: the 'data' fixtures are """

    def test_detail_expand_true_for_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that ligtInWijk shows up when expanded"""

        url = reverse("dynamic_api:gebieden-buurten-detail", args=["03630000000078.1"])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["ligtInWijk"]["id"] == "03630012052035.1"
        assert data["_embedded"]["ligtInWijk"]["_links"]["buurt"] == {
            "count": 2,  # counts historical records too.
            "href": "http://testserver/v1/gebieden/buurten/?ligtInWijkId=03630012052035.1",
        }

        assert data == {
            "_links": {
                "ligtInWijk": {
                    "href": "http://testserver/v1/gebieden/wijken/03630012052035/?volgnummer=1",
                    "identificatie": "03630012052035",
                    "title": "03630012052035.1",
                    "volgnummer": 1,
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                    "identificatie": "03630000000078",
                    "title": "03630000000078.1",
                    "volgnummer": 1,
                },
            },
            "beginGeldigheid": None,
            "code": None,
            "eindGeldigheid": None,
            "geometrie": None,
            "id": "03630000000078.1",
            "ligtInWijkId": "03630012052035",
            "naam": None,
            "_embedded": {
                "ligtInWijk": {
                    "_links": {
                        "schema": (
                            "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#wijken"
                        ),
                        "self": {
                            "href": (
                                "http://testserver/v1/gebieden/wijken/03630012052035/?volgnummer=1"
                            ),
                            "identificatie": "03630012052035",
                            "title": "03630012052035.1",
                            "volgnummer": 1,
                        },
                        "buurt": {
                            # See that the link is properly added
                            "count": 2,  # counts historical records too.
                            "href": (
                                "http://testserver/v1/gebieden/buurten/"
                                "?ligtInWijkId=03630012052035.1"
                            ),
                        },
                        "ligtInStadsdeel": {
                            "href": (
                                "http://testserver/v1/gebieden/stadsdelen/03630000000018/"
                                "?volgnummer=1"
                            ),
                            "identificatie": "03630000000018",
                            "title": "03630000000018.1",
                            "volgnummer": 1,
                        },
                    },
                    "id": "03630012052035.1",
                    "code": "A01",
                    "naam": "Burgwallen-Nieuwe Zijde",
                    "beginGeldigheid": None,
                    "eindGeldigheid": None,
                    "ligtInStadsdeelId": "03630000000018",
                    "_embedded": {
                        # second level embedded
                        "ligtInStadsdeel": {
                            "_links": {
                                "schema": (
                                    "https://schemas.data.amsterdam.nl"
                                    "/datasets/gebieden/dataset#stadsdelen"
                                ),
                                "self": {
                                    "href": (
                                        "http://testserver/v1/gebieden/stadsdelen/03630000000018/"
                                        "?volgnummer=1"
                                    ),
                                    "identificatie": "03630000000018",
                                    "title": "03630000000018.1",
                                    "volgnummer": 1,
                                },
                                # wijken is excluded (repeated relation)
                            },
                            "beginGeldigheid": None,
                            "code": "A",
                            "documentdatum": None,
                            "documentnummer": None,
                            "eindGeldigheid": None,
                            "geometrie": None,
                            "id": "03630000000018.1",
                            "naam": "Centrum",
                            "registratiedatum": None,
                        }
                    },
                }
            },
        }

    def test_nested_expand_list(
        self, api_client, panden_data, buurten_data, wijken_data, filled_router
    ):
        """Prove that nesting of nesting also works."""
        url = reverse("dynamic_api:bag-panden-list")
        response = api_client.get(
            url,
            data={
                "_expand": "true",
                "_expandScope": "ligtInBouwblok.ligtInBuurt.ligtInWijk.ligtInStadsdeel",
            },
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_embedded": {
                "panden": [
                    {
                        "_links": {
                            "schema": (
                                "https://schemas.data.amsterdam.nl/datasets/bag/dataset#panden"
                            ),
                            "self": {
                                "href": (
                                    "http://testserver/v1/bag/panden/0363100012061164/"
                                    "?volgnummer=3"
                                ),
                                "identificatie": "0363100012061164",
                                "title": "0363100012061164.3",
                                "volgnummer": 3,
                            },
                            "heeftDossier": {
                                "href": "http://testserver/v1/bag/dossiers/GV00000406/",
                                "title": "GV00000406",
                            },
                            "ligtInBouwblok": {
                                "href": (
                                    "http://testserver/v1/gebieden/bouwblokken/03630012096483/"
                                    "?volgnummer=1"
                                ),
                                "identificatie": "03630012096483",
                                "title": "03630012096483.1",
                                "volgnummer": 1,
                            },
                        },
                        "id": "0363100012061164.3",
                        "ligtInBouwblokId": "03630012096483",
                        "naam": "Voorbeeldpand",
                        "beginGeldigheid": None,
                        "eindGeldigheid": None,
                        "heeftDossierId": "GV00000406",
                    }
                ],
                "ligtInBouwblok": [
                    {
                        "_links": {
                            "schema": (
                                "https://schemas.data.amsterdam.nl"
                                "/datasets/gebieden/dataset#bouwblokken"
                            ),
                            "self": {
                                "href": (
                                    "http://testserver/v1/gebieden/bouwblokken/03630012096483/"
                                    "?volgnummer=1"
                                ),
                                "identificatie": "03630012096483",
                                "title": "03630012096483.1",
                                "volgnummer": 1,
                            },
                            "ligtInBuurt": {
                                "href": (
                                    "http://testserver/v1/gebieden/buurten/03630000000078/"
                                    "?volgnummer=2"
                                ),
                                "identificatie": "03630000000078",
                                "title": "03630000000078.2",
                                "volgnummer": 2,
                            },
                        },
                        "beginGeldigheid": None,
                        "code": None,
                        "eindGeldigheid": None,
                        "geometrie": None,
                        "id": "03630012096483.1",
                        "ligtInBuurtId": "03630000000078",
                        "registratiedatum": None,
                        "_embedded": {
                            "ligtInBuurt": {
                                "_links": {
                                    "schema": (
                                        "https://schemas.data.amsterdam.nl"
                                        "/datasets/gebieden/dataset#buurten"
                                    ),
                                    "self": {
                                        "href": (
                                            "http://testserver/v1/gebieden/buurten/03630000000078/"
                                            "?volgnummer=2"
                                        ),
                                        "identificatie": "03630000000078",
                                        "title": "03630000000078.2",
                                        "volgnummer": 2,
                                    },
                                    "ligtInWijk": {
                                        "href": (
                                            "http://testserver/v1/gebieden/wijken/03630012052035/"
                                            "?volgnummer=1"
                                        ),
                                        "identificatie": "03630012052035",
                                        "title": "03630012052035.1",
                                        "volgnummer": 1,
                                    },
                                },
                                "id": "03630000000078.2",
                                "naam": None,
                                "code": None,
                                "geometrie": None,
                                "beginGeldigheid": None,
                                "eindGeldigheid": None,
                                "ligtInWijkId": "03630012052035",
                                "_embedded": {
                                    "ligtInWijk": {
                                        "_embedded": {
                                            "ligtInStadsdeel": {
                                                "_links": {
                                                    "schema": (
                                                        "https://schemas.data.amsterdam.nl"
                                                        "/datasets/gebieden/dataset#stadsdelen"
                                                    ),
                                                    "self": {
                                                        "href": (
                                                            "http://testserver/v1"
                                                            "/gebieden/stadsdelen/03630000000018/"
                                                            "?volgnummer=1"
                                                        ),
                                                        "identificatie": "03630000000018",
                                                        "title": "03630000000018.1",
                                                        "volgnummer": 1,
                                                    },
                                                    # wijken is excluded (repeated relation)
                                                },
                                                "beginGeldigheid": None,
                                                "code": "A",
                                                "documentdatum": None,
                                                "documentnummer": None,
                                                "eindGeldigheid": None,
                                                "geometrie": None,
                                                "id": "03630000000018.1",
                                                "naam": "Centrum",
                                                "registratiedatum": None,
                                            }
                                        },
                                        "_links": {
                                            "schema": (
                                                "https://schemas.data.amsterdam.nl"
                                                "/datasets/gebieden/dataset#wijken"
                                            ),
                                            "self": {
                                                "href": (
                                                    "http://testserver/v1"
                                                    "/gebieden/wijken/03630012052035/"
                                                    "?volgnummer=1"
                                                ),
                                                "identificatie": "03630012052035",
                                                "title": "03630012052035.1",
                                                "volgnummer": 1,
                                            },
                                            "buurt": {
                                                "count": 2,
                                                "href": (
                                                    "http://testserver/v1/gebieden/buurten/"
                                                    "?ligtInWijkId=03630012052035.1"
                                                ),
                                            },
                                            "ligtInStadsdeel": {
                                                "href": (
                                                    "http://testserver/v1"
                                                    "/gebieden/stadsdelen/03630000000018/"
                                                    "?volgnummer=1"
                                                ),
                                                "identificatie": "03630000000018",
                                                "title": "03630000000018.1",
                                                "volgnummer": 1,
                                            },
                                        },
                                        "beginGeldigheid": None,
                                        "code": "A01",
                                        "eindGeldigheid": None,
                                        "id": "03630012052035.1",
                                        "ligtInStadsdeelId": "03630000000018",
                                        "naam": "Burgwallen-Nieuwe " "Zijde",
                                    }
                                },
                            }
                        },
                    }
                ],
            },
            "_links": {
                "self": {
                    "href": (
                        "http://testserver/v1/bag/panden/?_expand=true"
                        "&_expandScope=ligtInBouwblok.ligtInBuurt.ligtInWijk.ligtInStadsdeel"
                    )
                }
            },
            "page": {"number": 1, "size": 20},
        }

    def test_detail_no_expand_for_temporal_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that temporal identifier fields have been removed from the body
        and only appear in the respective HAL envelopes"""

        url = reverse("dynamic_api:gebieden-buurten-detail", args=["03630000000078.1"])
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "ligtInWijk": {
                    "href": "http://testserver/v1/gebieden/wijken/03630012052035/?volgnummer=1",
                    "identificatie": "03630012052035",
                    "title": "03630012052035.1",
                    "volgnummer": 1,
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                    "identificatie": "03630000000078",
                    "title": "03630000000078.1",
                    "volgnummer": 1,
                },
            },
            "beginGeldigheid": None,
            "code": None,
            "eindGeldigheid": None,
            "geometrie": None,
            "id": "03630000000078.1",
            "ligtInWijkId": "03630012052035",
            "naam": None,
        }

    def test_list_expand_true_for_fk_relation(
        self, api_client, buurten_data, wijken_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-buurten-list")
        url = f"{url}?_format=json&_expand=true"
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["ligtInWijk"][0]["id"] == "03630012052035.1"
        assert data["_embedded"]["ligtInWijk"][0]["_links"]["buurt"] == {
            "count": 2,  # counts historical records too.
            "href": (
                "http://testserver/v1/gebieden/buurten/"
                "?_format=json&ligtInWijkId=03630012052035.1"
            ),
        }
        assert data == {
            "_embedded": {
                "buurten": [
                    # Main response
                    {
                        "_links": {
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/buurten/03630000000078/?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630000000078",
                                "title": "03630000000078.1",
                                "volgnummer": 1,
                            },
                            "ligtInWijk": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035/?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                        },
                        "id": "03630000000078.1",
                        "naam": None,
                        "code": None,
                        "beginGeldigheid": None,
                        "eindGeldigheid": None,
                        "geometrie": None,
                        "ligtInWijkId": "03630012052035",
                    },
                    {
                        "_links": {
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/buurten/03630000000078/?_format=json&volgnummer=2",  # noqa: E501
                                "identificatie": "03630000000078",
                                "title": "03630000000078.2",
                                "volgnummer": 2,
                            },
                            "ligtInWijk": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035/?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                        },
                        "id": "03630000000078.2",
                        "code": None,
                        "naam": None,
                        "beginGeldigheid": None,
                        "eindGeldigheid": None,
                        "geometrie": None,
                        "ligtInWijkId": "03630012052035",
                    },
                ],
                "ligtInWijk": [
                    # Embedded object in next section
                    {
                        "_links": {
                            "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#wijken",  # noqa: E501
                            "self": {
                                "href": "http://testserver/v1/gebieden/wijken/03630012052035/?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630012052035",
                                "title": "03630012052035.1",
                                "volgnummer": 1,
                            },
                            "buurt": {
                                "count": 2,
                                "href": "http://testserver/v1/gebieden/buurten/?_format=json&ligtInWijkId=03630012052035.1",  # noqa: E501
                            },
                            "ligtInStadsdeel": {
                                "href": "http://testserver/v1/gebieden/stadsdelen/03630000000018/?_format=json&volgnummer=1",  # noqa: E501
                                "identificatie": "03630000000018",
                                "title": "03630000000018.1",
                                "volgnummer": 1,
                            },
                        },
                        "beginGeldigheid": None,
                        "code": "A01",
                        "eindGeldigheid": None,
                        "id": "03630012052035.1",
                        "ligtInStadsdeelId": "03630000000018",
                        "naam": "Burgwallen-Nieuwe Zijde",
                        "_embedded": {
                            # Nested embedding (1 level)
                            "ligtInStadsdeel": {
                                "_links": {
                                    "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#stadsdelen",  # noqa: E501
                                    "self": {
                                        "href": "http://testserver/v1/gebieden/stadsdelen/03630000000018/?_format=json&volgnummer=1",  # noqa: E501
                                        "identificatie": "03630000000018",
                                        "title": "03630000000018.1",
                                        "volgnummer": 1,
                                    },
                                    # wijken is excluded here (forward/reverse relation loop)
                                },
                                "beginGeldigheid": None,
                                "code": "A",
                                "documentdatum": None,
                                "documentnummer": None,
                                "eindGeldigheid": None,
                                "geometrie": None,
                                "id": "03630000000018.1",
                                "naam": "Centrum",
                                "registratiedatum": None,
                            }
                        },
                    }
                ],
            },
            "_links": {
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/?_format=json&_expand=true"
                }
            },
            "page": {"number": 1, "size": 20},
        }

    def test_detail_expand_true_for_nm_relation(
        self, api_client, buurten_data, ggwgebieden_data, filled_router
    ):
        """Prove that bestaatUitBuurten shows up when expanded"""

        url = reverse("dynamic_api:gebieden-ggwgebieden-detail", args=["03630950000000.1"])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["bestaatUitBuurten"][0]["id"] == "03630000000078.1"

    def test_list_expand_true_for_nm_relation(
        self, api_client, buurten_data, ggwgebieden_data, woningbouwplannen_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert dict(data["_embedded"]["bestaatUitBuurten"][0]) == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",
                "self": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                    "title": "03630000000078.1",
                    "volgnummer": 1,
                    "identificatie": "03630000000078",
                },
            },
            "geometrie": None,
            "naam": None,
            "code": None,
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "id": "03630000000078.1",
            "ligtInWijkId": "03630012052035",
            "_embedded": {
                "ligtInWijk": None,
            },
        }
        assert dict(data["_embedded"]["ggwgebieden"][0]) == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#ggwgebieden",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/gebieden/ggwgebieden/03630950000000/?volgnummer=1",  # noqa: E501
                    "title": "03630950000000.1",
                    "volgnummer": 1,
                    "identificatie": "03630950000000",
                },
                "bestaatUitBuurten": [
                    {
                        "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",  # noqa: E501
                        "title": "03630000000078.1",
                        "volgnummer": 1,
                        "identificatie": "03630000000078",
                    },
                ],
            },
            "geometrie": None,
            "id": "03630950000000.1",
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "naam": None,
            "registratiedatum": None,
        }

    def test_through_extra_fields_for_nm_relation(
        self, api_client, buurten_data, ggpgebieden_data, filled_router
    ):
        """Prove that extra through fields are showing up
        latest volgnummer
        """

        url = reverse("dynamic_api:gebieden-ggpgebieden-list")
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert dict(data["_embedded"]["ggpgebieden"][0]) == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#ggpgebieden",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/gebieden/ggpgebieden/03630950000000/?volgnummer=1",  # noqa: E501
                    "title": "03630950000000.1",
                    "volgnummer": 1,
                    "identificatie": "03630950000000",
                },
                "bestaatUitBuurten": [
                    {
                        "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=1",  # noqa: E501
                        "title": "03630000000078.1",
                        "volgnummer": 1,
                        "identificatie": "03630000000078",
                        "beginGeldigheid": "2020-01-04",
                        "eindGeldigheid": None,
                    },
                ],
            },
            "geometrie": None,
            "id": "03630950000000.1",
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "naam": None,
            "registratiedatum": None,
        }

    def test_detail_no_expand_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Without _expand=true there is no _embedded field.
        The buurt link must appear in the _links field inside an HAL envelope.
        The "buurtId" field in is how the field is known in the statistieken dataset, and must
        appear in the body of the response.
        The buurt link is not resolved to the latest volgnummer, but "identificatie" is specified,
        which is the identifier used by the gebieden dataset.
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "buurt": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/",
                    "title": "03630000000078",
                    "identificatie": "03630000000078",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/dataset#statistieken",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1/",
                    "title": "1",
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
        }

    def test_detail_expand_true_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Prove that buurt shows up when expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:meldingen-statistieken-detail", args=[1])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/meldingen/dataset#statistieken",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/meldingen/statistieken/1/",
                    "title": "1",
                },
                "buurt": {
                    "href": "http://testserver/v1/gebieden/buurten/03630000000078/",
                    "identificatie": "03630000000078",
                    "title": "03630000000078",
                },
            },
            "id": 1,
            "buurtId": "03630000000078",
            "_embedded": {
                "buurt": {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#buurten",  # noqa: E501
                        "self": {
                            "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2",  # noqa: E501
                            "title": "03630000000078.2",
                            "volgnummer": 2,
                            "identificatie": "03630000000078",
                        },
                    },
                    "code": None,
                    "naam": None,
                    "geometrie": None,
                    "eindGeldigheid": None,
                    "beginGeldigheid": None,
                    "id": "03630000000078.2",
                    "ligtInWijkId": "03630012052035.1",
                    "_embedded": {
                        "ligtInWijk": None,
                    },
                }
            },
        }

    def test_list_expand_true_for_loose_relation(
        self, api_client, statistieken_data, buurten_data, filled_router
    ):
        """Prove that buurt shows up when listview is expanded and uses the
        latest volgnummer
        """

        url = reverse("dynamic_api:meldingen-statistieken-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_embedded"]["buurt"][0]["id"] == "03630000000078.2"
        assert data["_embedded"]["buurt"][0]["_links"]["self"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2",
            "identificatie": "03630000000078",
            "title": "03630000000078.2",
            "volgnummer": 2,
        }
        assert data["_embedded"]["statistieken"][0]["id"] == 1
        assert data["_embedded"]["statistieken"][0]["_links"]["buurt"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078/",
            "title": "03630000000078",
            "identificatie": "03630000000078",
        }
        assert "_embedded" not in data["_embedded"]["statistieken"][0]

    def test_list_expand_true_non_tempooral_many_to_many_to_temporal(
        self, api_client, buurten_data, woningbouwplannen_data, filled_router
    ):
        """_embedded must contain for each FK or MN relation a key (with camelCased fieldname)
        containing a list of all records that are being referred to
        for loose relations, these must be resolved to the latest 'volgnummer'
        _embedded must also contain a key (with table name)
          containing a (filtered) list of items.
        the FK or NM relation keys in those items are urls without volgnummer

        Check the loose coupling of woningbouwplan with buurten
        The "identificatie" fieldname is taken from the related buurten model.
        Note that "volgnummer" is not specified within the woningbouwplan data (which
        makes it "loose"), and therefore not mentioned here"""

        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-list")
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data

        #  _embedded must contain for each FK or MN relation a key (with camelCased fieldname)
        #  containing a list of all records that are being referred to
        #  for loose relations, these must be resolved to the latest 'volgnummer'
        #  _embedded must also contain a key (with table name)
        #    containing a (filtered) list of items.
        # the FK or NM relation keys in those items are urls without volgnummer

        assert data["_embedded"]["buurten"][0]["id"] == "03630000000078.2"
        assert data["_embedded"]["woningbouwplan"][0]["_links"]["buurten"] == [
            {
                "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2",
                "title": "03630000000078.2",
                "identificatie": "03630000000078",
                "volgnummer": 2,
            }
        ]
        #  Check that the embedded buurten contains the correct "identificatie",
        #  and is now also resolved to the latest "volgnummer", which is specified.
        assert data["_embedded"]["buurten"][0]["_links"]["self"] == {
            "href": "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2",
            "title": "03630000000078.2",
            "identificatie": "03630000000078",
            "volgnummer": 2,
        }
        #  Check "id" is resolved to correct identificatie.volgnummer format
        assert data["_embedded"]["buurten"][0]["id"] == "03630000000078.2"

    def test_detail_expand_true_non_temporal_many_to_many_to_temporal(
        self,
        api_client,
        woningbouwplan_model,
        woningbouwplannen_data,
        filled_router,
    ):
        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-detail", args=[1])
        response = api_client.get(url, data={"_expand": "true"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert "buurten" not in data  # because it must be in  "_embedded"
        buurten = data["_embedded"]["buurten"]
        assert buurten[0]["id"] == "03630000000078.2"
        assert buurten[0]["_links"]["self"]["href"] == (
            "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2"
        )

    def test_independence_of_m2m_through_id_field(
        self,
        api_client,
        buurten_data,
        woningbouwplannen_data,
        filled_router,
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
        column_names_before = {column_name for (column_name,) in cursor.fetchall()}
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
        column_names_after = {column_name for (column_name,) in cursor.fetchall()}
        assert "wbw_rel_woningbouwplan_buurt_id" in column_names_after
        assert "id" not in column_names_after
        url = reverse("dynamic_api:woningbouwplannen-woningbouwplan-detail", args=[1])
        response = api_client.get(url)
        data = read_response_json(response)

        # check that "buurten" still contains the correct list
        assert (
            data["_links"]["buurten"][0]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/?volgnummer=2"
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
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            b"1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992;"
            b"POINT (10 10)\r\n",
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
                        "id": "containers.1",
                        "geometry": {
                            "type": "Point",
                            "coordinates": GEOJSON_POINT,
                        },
                        "properties": {
                            "id": 1,
                            "clusterId": "c1",
                            "serienummer": "foobar-123",
                            "eigenaarNaam": "Dataservices",
                            "datumCreatie": "2021-01-03",
                            "datumLeegmaken": "2021-01-03T12:13:14",
                        },
                    }
                ],
                "_links": [],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(UNPAGINATED_FORMATS.keys()))
    def test_unpaginated_list(self, format, api_client, afval_container, filled_router):
        """Prove that the export formats generate proper data."""
        decoder, expected_type, expected_data = self.UNPAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading
        assert response["Content-Disposition"].startswith(
            'attachment; filename="afvalwegingen-containers'
        )

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
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            b"1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (10 10)\r\n"
            b"2,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (10 10)\r\n"
            b"3,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (10 10)\r\n"
            b"4,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (10 10)\r\n",
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
                        "id": f"containers.{i}",
                        "geometry": {
                            "type": "Point",
                            "coordinates": GEOJSON_POINT,
                        },
                        "properties": {
                            "id": i,
                            "clusterId": "c1",
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
    def test_paginated_list(self, format, api_client, afval_container, filled_router):
        """Prove that the pagination still works if explicitly requested."""
        decoder, expected_type, expected_data = self.PAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        for i in range(2, 10):
            afval_container.id = i
            afval_container.save()

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format, "_pageSize": "4"})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was triggered
        assert response["X-Pagination-Page"] == "1"
        assert response["X-Pagination-Limit"] == "4"

        # proves middleware detected streaming response, and didn't break it:
        assert "Content-Length" not in response

        # Check that the response is streaming:
        assert response.streaming
        assert inspect.isgeneratorfunction(response.accepted_renderer.render)

    EMPTY_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n",
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
    def test_empty_list(self, format, api_client, afval_dataset, filled_router):
        """Prove that empty list pages are properly serialized."""
        decoder, expected_type, expected_data = self.EMPTY_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

    def test_csv_expand_inline(
        self, api_client, api_rf, afval_container, fetch_auth_token, filled_router
    ):
        """Prove that the expand logic works, which is implemented inline for CSV"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/R"])  # needed in afval.json to fetch cluster
        response = api_client.get(
            url,
            {"_format": "csv", "_expandScope": "cluster"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response["Content-Type"] == "text/csv; charset=utf-8"  # Test before reading stream
        assert response["Content-Disposition"].startswith(
            'attachment; filename="afvalwegingen-containers'
        )

        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = read_response(response)
        assert data == (
            "Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry"
            ",Cluster.Id,Cluster.Status\r\n"
            "1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992;POINT (10 10)"
            ",c1,valid\r\n"
        )

    def test_csv_expand_m2m_invalid(self, api_client, api_rf, ggwgebieden_data, filled_router):
        """Prove that the expand logic works, which is implemented inline for CSV"""
        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        api_client.raise_request_exception = False
        response = api_client.get(url, {"_format": "csv", "_expandScope": "bestaatUitBuurten"})
        assert response.status_code == 400, response.getvalue()
        data = read_response_json(response)
        assert data == {
            "detail": (
                "Eager loading is not supported for field 'bestaatUitBuurten' "
                "in this output format"
            ),
            "status": 400,
            "title": "Malformed request.",
            "type": "urn:apiexception:parse_error",
        }

    def test_csv_expand_skip_m2m(self, api_client, api_rf, ggwgebieden_data, filled_router):
        """Prove that the expand logic works, but skips M2M relations for auto-expand-all"""
        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        api_client.raise_request_exception = False
        response = api_client.get(url, {"_format": "csv", "_expand": "true"})
        assert response.status_code == 200, response.getvalue()
        data = read_response(response)

        # fields don't include bestaatUitBuurten
        assert data == (
            "Registratiedatum,Naam,Begingeldigheid,Eindgeldigheid,Geometrie,Id\r\n"
            ",,,,,03630950000000.1\r\n"
        )

    DETAIL_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            b"1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (10 10)\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "Feature",
                "id": "containers.1",
                "geometry": {
                    "coordinates": GEOJSON_POINT,
                    "type": "Point",
                },
                "properties": {
                    "id": 1,
                    "clusterId": "c1",
                    "serienummer": "foobar-123",
                    "eigenaarNaam": "Dataservices",
                    "datumCreatie": "2021-01-03",
                    "datumLeegmaken": "2021-01-03T12:13:14",
                },
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4326"},
                    "type": "name",
                },
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail(self, format, api_client, afval_container, filled_router):
        """Prove that the detail view also returns an export of a single feature."""
        decoder, expected_type, expected_data = self.DETAIL_FORMATS[format]
        url = reverse(
            "dynamic_api:afvalwegingen-containers-detail",
            kwargs={"pk": afval_container.pk},
        )

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was NOT triggered
        assert "X-Pagination-Page" not in response

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail_404(self, format, api_client, afval_dataset, filled_router):
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
