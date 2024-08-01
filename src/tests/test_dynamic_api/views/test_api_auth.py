import pytest
from django.urls import reverse
from schematools.contrib.django import models
from schematools.types import ProfileSchema

from tests.utils import patch_dataset_auth, patch_field_auth, patch_table_auth, read_response_json


@pytest.mark.django_db
class TestAuth:
    """Test authorization"""

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
                                        ["regimes.eindtijd"],
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

        def _assert_get(token, params="", expect=200):
            response = api_client.get(f"{base_url}{params}", HTTP_AUTHORIZATION=f"Bearer {token}")
            data = read_response_json(response)
            assert response.status_code == expect, data
            return data

        token = fetch_auth_token(["PROFIEL/SCOPE"])
        base_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        assert api_client.get(base_url).status_code == 403
        _assert_get(token, expect=403)

        # See that only the proper filters activate the profile (via mandatoryFilterSets)
        _assert_get(token, "?buurtcode=A05d", expect=403)
        _assert_get(token, "?buurtcode=A05d&type=E9", expect=200)
        _assert_get(token, "?regimes.eindtijd=20:05", expect=200)
        _assert_get(token, "?regimes.eindtijd=", expect=403)
        _assert_get(token, "?regimes.eindtijd", expect=403)

        # See that 'auth' satisfies without needing a profile
        token2 = fetch_auth_token(["DATASET/SCOPE", "PROFIEL/SCOPE"])
        _assert_get(token2, expect=200)

        token3 = fetch_auth_token(["DATASET/SCOPE"])
        _assert_get(token3, expect=200)

        # See that both profiles can be active
        token4 = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        # TODO should be 400.
        _assert_get(token4, "?regimes.noSuchField=whatever", expect=403)
        _assert_get(token4, "?regimes.aantal[gte]=2", expect=200)

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
        # Using 'detail' URL because filtering on ?id=..
        # is prohibited when the field is not accessible.
        token = fetch_auth_token(["PROFIEL/SCOPE"])
        list_url = reverse("dynamic_api:parkeervakken-parkeervakken-list")
        detail_url = reverse("dynamic_api:parkeervakken-parkeervakken-detail", args=("1",))
        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/", "id": "1"},
            },
            # no ID field (not authorized)
            "soort": "N",  # letters:1
            "type": "Langs",  # read permission
        }

        # 2) profile and dataset scope -> all allowed (auth of dataset is satisfied)
        token = fetch_auth_token(["PROFIEL/SCOPE", "DATASET/SCOPE"])
        response = api_client.get(f"{list_url}?id=1", HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        parkeervak_data = data["_embedded"]["parkeervakken"][0]
        assert parkeervak_data == {
            "_links": {
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/parkeervakken/dataset#parkeervakken"
                ),
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/", "id": "1"},
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
            "volgnummer": None,
        }

        # 3) two profile scopes, only one matches (mandatory filtersets)
        token = fetch_auth_token(["PROFIEL/SCOPE", "PROFIEL2/SCOPE"])
        # trigger one profile
        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/", "id": "1"},
            },
            "soort": "N",  # letters:1
            "type": "Langs",  # read permission
        }

        # 4) both profiles + mandatory filtersets
        response = api_client.get(f"{detail_url}?type=Langs", HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/1/", "id": "1"},
            },
            "type": "Langs",  # read permission
            "soort": "NIET FISCA",  # read permission
        }

    @pytest.mark.parametrize("table_name", ["containers", "clusters"])
    def test_auth_on_dataset(
        self, api_client, afval_schema, afval_dataset, filled_router, table_name
    ):
        """Prove that auth protection at dataset level leads to a 403 on the table listviews."""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse(f"dynamic_api:afvalwegingen-{table_name}-list")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table(self, api_client, afval_schema, afval_dataset, filled_router):
        """Prove that auth protection at table level (container)
        leads to a 403 on the container listview."""
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_does_not_protect_sibling_tables(
        self, api_client, fetch_auth_token, afval_schema, afval_dataset, filled_router
    ):
        """Prove that auth protection at table level (cluster)
        does not protect the container list view."""
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200, response.data

    @pytest.mark.parametrize(["token_scope", "expect_code"], [("BAG/R", 200), ("BAG/RSN", 403)])
    def test_auth_on_table_with_token(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        token_scope,
        expect_code,
    ):
        """Prove that auth protected table (container) can be
        viewed with a token with the correct scope."""
        patch_table_auth(afval_schema, "containers", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token([token_scope])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == expect_code, response.data

    @pytest.mark.parametrize(
        ["token_scope", "expect_expand"],
        [
            ("BAG/R", True),
            ("BAG/NOPE", False),
        ],
    )
    def test_auth_on_embedded_fields_expand_all(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        token_scope,
        expect_expand,
    ):
        """Prove that expanded fields are shown when a reference field is protected
        with an auth scope and there is a valid token.

        When the expanded field is auth-protected,
        it will not be included in th default _expand=true.
        """
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token([token_scope])
        response = api_client.get(
            url, data={"_expand": "true"}, HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert ("cluster" in data["_embedded"]) == expect_expand, data

    @pytest.mark.parametrize(["use_token", "expect_code"], [(True, 200), (False, 403)])
    def test_auth_on_embedded_fields_expand_specific(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        use_token,
        expect_code,
    ):
        """Prove that a 403 is returned when asked for a specific expanded field that is protected
        and there is no authorization in the token for that field.
        """
        patch_table_auth(afval_schema, "clusters", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        header = (
            {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token(['BAG/R'])}"} if use_token else {}
        )
        response = api_client.get(url, data={"_expandScope": "cluster"}, **header)
        assert response.status_code == expect_code, response.data

    @pytest.mark.parametrize(
        ["token_scope", "expect_field"],
        [
            ("BAG/R", True),
            ("BAG/NOT", False),
            ("", False),
        ],
    )
    def test_auth_on_field(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        token_scope,
        expect_field,
    ):
        """Prove that protected fields are shown/hidden depending on the token.
        This is tested with an valid/invalid/missing token."""
        patch_field_auth(afval_schema, "containers", "eigenaarNaam", auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # First fetch should NOT return the field,
        # Second fetch should with token should return the field.
        header = (
            {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token([token_scope])}"}
            if token_scope
            else {}
        )
        response = api_client.get(url, **header)
        data = read_response_json(response)

        assert response.status_code == 200, data
        field_names = data["_embedded"]["containers"][0].keys()
        assert ("eigenaarNaam" in field_names) == expect_field, field_names

    @pytest.mark.parametrize("use_header", (False, True))
    def test_auth_on_field_via_profile(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        use_header,
    ):
        """Prove that protected fields are shown
        with an auth scope connected to Profile that gives access to specific field."""
        patch_field_auth(afval_schema, "containers", "eigenaarNaam", auth=["BAG/R"])
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
                                        "eigenaarNaam": "read",
                                    }
                                }
                            }
                        }
                    },
                }
            )
        )
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BRK/RO", "BRK/RSN"])  # not BAG/R

        # First fetch should NOT return the field,
        # Second fetch should with token should return the field.
        header = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if use_header else {}
        response = api_client.get(url, **header)
        data = read_response_json(response)

        assert response.status_code == 200, data
        field_names = data["_embedded"]["containers"][0].keys()
        assert ("eigenaarNaam" in field_names) == use_header, field_names  # profile read access

    @pytest.mark.parametrize("use_header", (False, True))
    def test_auth_on_field_level_is_not_cached(
        self,
        api_client,
        fetch_auth_token,
        parkeervakken_schema,
        parkeervak,
        filled_router,
        use_header,
    ):
        """Prove that Auth is not cached."""
        patch_field_auth(parkeervakken_schema, "parkeervakken", "regimes", "dagen", auth=["BAG/R"])
        url = reverse("dynamic_api:parkeervakken-parkeervakken-list")

        # First fetch without BAG/R token, should not return field
        # Second fetch with BAG/R token, should return field.
        token = fetch_auth_token(["BAG/R"])
        header = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if use_header else {}
        response = api_client.get(url, **header)
        data = read_response_json(response)

        field_names = data["_embedded"]["parkeervakken"][0]["regimes"][0].keys()
        assert ("dagen" in field_names) == use_header, field_names

    @pytest.mark.parametrize(
        ["token_scope", "expect_code"],
        [
            ("BAG/R", 200),
            ("BAG/NOPE", 403),
            ("", 403),
        ],
    )
    def test_detail_view_dataset_auth(
        self,
        api_client,
        fetch_auth_token,
        afval_schema,
        afval_container,
        filled_router,
        token_scope,
        expect_code,
    ):
        """Prove that protection at datasets level protects detail views"""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-containers-detail", args=[1])
        header = (
            {"HTTP_AUTHORIZATION": f"Bearer {fetch_auth_token([token_scope])}"}
            if token_scope
            else {}
        )
        response = api_client.get(url, **header)
        assert response.status_code == expect_code, response.data

    def test_detail_view_auth_on_dataset_via_profiles(
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
        assert response.status_code == 404, response.data

        response = api_client.get(detail_url, HTTP_AUTHORIZATION=f"Bearer {dataset_scope}")
        assert response.status_code == 200, response.data

        response = api_client.get(
            detail_url, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}"
        )
        assert response.status_code == 403, response.data

        response = api_client.get(
            detail_met_volgnummer, HTTP_AUTHORIZATION=f"Bearer {profiel_met_volgnummer}"
        )
        assert response.status_code == 404, response.data

    def test_auth_options_requests_are_not_protected(
        self, api_client, afval_schema, afval_dataset, filled_router
    ):
        """Prove that options requests are not protected"""
        patch_dataset_auth(afval_schema, auth=["BAG/R"])
        url = reverse("dynamic_api:afvalwegingen-clusters-list")
        response = api_client.options(url)
        assert response.status_code == 200, response.data

    @pytest.fixture
    def patched_afval_schema(self, afval_schema):
        patch_field_auth(afval_schema, "containers", "datumCreatie", auth=["SEE/CREATION"])
        return afval_schema

    def test_sort_auth(self, api_client, patched_afval_schema, afval_container, filled_router):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datumCreatie")
        data = read_response_json(response)
        assert response.status_code == 403, data
        assert data["title"] == "Access denied to filter on: datumCreatie"

    def test_sort_by_not_accepting_db_column_names(
        self, api_client, afval_container, filled_router
    ):
        """Prove that _sort is not accepting db column names."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(f"{url}?_sort=datum_creatie")
        data = read_response_json(response)
        assert response.status_code == 400, data
        assert data["invalid-params"][0] == {
            "type": "urn:apiexception:invalid:invalid",
            "name": "invalid",
            "reason": "Field 'datum_creatie' does not exist",
        }

    def test_array_of_nested_auth(
        self, api_client, dynamic_models, fetch_auth_token, array_auth, filled_router
    ):
        url = reverse("dynamic_api:arrayauth-things-list")
        thing = dynamic_models["arrayauth"]["things"].objects.create(id=1)
        dynamic_models["arrayauth"]["things_secret_array"].objects.create(parent=thing)

        token = fetch_auth_token(["AUTH/DATASET", "AUTH/TABLE"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert "secretArray" not in data["_embedded"]["things"][0]

        token = fetch_auth_token(["AUTH/DATASET", "AUTH/TABLE", "AUTH/FIELD"])
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        data = read_response_json(response)
        assert "secretArray" in data["_embedded"]["things"][0]
