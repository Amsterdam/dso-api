import pytest
from django.contrib.gis.geos import GEOSGeometry
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST

from tests.utils import read_response_json


@pytest.mark.django_db
class TestFilterParsing:
    """Prove that filter parsing works as expected."""

    @staticmethod
    def test_no_such_field(api_client, afval_dataset, filled_router):
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Non-existing field.
        response = api_client.get(url, data={"nonexistent": ""})
        assert response.status_code == HTTP_400_BAD_REQUEST, response.data
        reason = response.data["invalid-params"][0]["reason"]
        assert reason == "Field 'nonexistent' does not exist"

    @staticmethod
    @pytest.mark.parametrize(
        "url",
        [
            "/v1/movies/movie/?nonexistent=foo123",  # invalid normal field
            "/v1/movies/movie/?name.nonexistent=foo123",  # not a relation
            "/v1/movies/category/?movies.nonexistent=foo123",  # using reverse FK
            "/v1/movies/category/?movies.name.nonexistent=foo123",  # using reverse FK
            "/v1/movies/actor/?movies.nonexistent=foo123",  # using reverse M2M
            "/v1/movies/actor/?movies.name.nonexistent=foo123",  # using reverse M2M
        ],
    )
    def test_invalid_relations(api_client, movies_model, filled_router, url):
        """Prove that walking over M2M models works and doesn't crash the parser.
        Note this uses the "movies" dataset, not the hardcoded movie models/serializers.
        """
        response = api_client.get(url)
        data = read_response_json(response)
        assert response.status_code == 400, data

    @staticmethod
    @pytest.mark.parametrize(
        ["query", "expect_code"],
        [
            ("regimes.dagen=ma,di,wo,do,vr", 200),
            ("regimes.dagen.foo=test", 400),
            ("regimes.foo=test", 400),  # subfield has different codepath if not found.
            ("foobar=test", 400),
            ("e_type=whatever", 400),  # no snake_cases
            ("_sort=e_type", 400),  # no snake_cases
        ],
    )
    def test_invalid_subfield(
        api_client, parkeervakken_parkeervak_model, parkeervakken_regime_model, query, expect_code
    ):
        """Prove that looking for a relation on a nested field won't crash."""
        response = api_client.get(f"/v1/parkeervakken/parkeervakken/?{query}")
        data = read_response_json(response)
        assert response.status_code == expect_code, data

    @staticmethod
    @pytest.mark.parametrize(
        "param",
        [
            "buurtcode[",
            "buurtcode[exact",
            "buurtcodeexact]",
        ],
    )
    def test_syntax_error(param, api_client, afval_dataset, filled_router):
        """Existing field, but syntax error in the filter parameter."""
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        response = api_client.get(url, data={param: ""})
        assert response.status_code == HTTP_400_BAD_REQUEST, response.data
        reason = response.data["invalid-params"][0]["reason"]
        assert param in reason


@pytest.mark.django_db
class TestFilterFieldTypes:
    @staticmethod
    @pytest.mark.parametrize(
        "lookup,expect",
        [
            ("", 0),
            ("[like]", 1),
        ],
    )
    def test_list_filter_wildcard(api_client, movies_data, filled_router, lookup, expect):
        """Prove that ?name=foo doesn't work with wildcards (that now requires [like]).
        Second parameterized call tests whether using [like] does produce the desired effect.
        """
        response = api_client.get("/v1/movies/movie/", data={f"name{lookup}": "foo1?3"})
        assert response.status_code == 200, response
        assert response["Content-Type"] == "application/hal+json"
        data = read_response_json(response)
        assert len(data["_embedded"]["movie"]) == expect

    @staticmethod
    def test_list_filter_datetime(api_client, movies_data, filled_router):
        """Prove that datetime fields can be queried using a single data value"""
        response = api_client.get("/v1/movies/movie/", data={"dateAdded": "2020-01-01"})
        data = read_response_json(response)
        assert response.status_code == 200, response
        assert response["Content-Type"] == "application/hal+json"
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["foo123"]

    @staticmethod
    def test_list_filter_datetime_invalid(api_client, movies_data, filled_router):
        """Prove that invalid input is captured, and returns a proper error response."""
        response = api_client.get("/v1/movies/movie/", data={"dateAdded": "2020-01-fubar"})
        assert response.status_code == 400, response
        assert response["Content-Type"] == "application/problem+json", response  # check first
        data = read_response_json(response)
        assert response["Content-Type"] == "application/problem+json", response  # and after
        assert data == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies/movie/?dateAdded=2020-01-fubar",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:invalid",
                    "name": "dateAdded",
                    "reason": "Enter a valid ISO date-time, or single date.",
                }
            ],
            "x-validation-errors": {"dateAdded": ["Enter a valid ISO date-time, or single date."]},
        }

    @pytest.mark.django_db
    def test_relation_filter(
        self, api_client, vestiging_dataset, vestiging1, vestiging2, filled_router
    ):
        url = reverse("dynamic_api:vestiging-vestiging-list")
        response = api_client.get(url)
        assert response.status_code == HTTP_200_OK
        data = read_response_json(response)
        assert len(data["_embedded"]["vestiging"]) == 2

        response = api_client.get(url, data={"bezoekAdresId": "1"})
        assert response.status_code == HTTP_200_OK, response.data
        data = read_response_json(response)
        assert len(data["_embedded"]["vestiging"]) == 1
        assert data["_embedded"]["vestiging"][0]["bezoekAdresId"] == 1

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("regimes.dagen=ma,di,wo,do,vr", 1),
            ("regimes.dagen=ma,di,wo,do", 0),
            ("regimes.dagen=ma,di,wo,do,vr,za,zo", 1),
            ("regimes.dagen[contains]=ma,wo", 1),
            ("regimes.dagen[contains]=ma,wo,foo", 0),
        ],
    )
    def test_array_field(api_client, parkeervak, query, expect):
        response = api_client.get(f"/v1/parkeervakken/parkeervakken/?{query}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert len(data["_embedded"]["parkeervakken"]) == expect

    @staticmethod
    def test_numerical_filters(api_client, parkeervakken_parkeervak_model, filled_router):
        """Test comparisons on numerical fields."""

        p1 = parkeervakken_parkeervak_model.objects.create(id="p1", aantal=1)
        p2 = parkeervakken_parkeervak_model.objects.create(id="p2", aantal=2)
        p5 = parkeervakken_parkeervak_model.objects.create(id="p5", aantal=5)

        for op, filter_aantal, expect in [
            ("lte", 1, [p1]),
            ("gt", 3, [p5]),
            ("lt", 3, [p1, p2]),
            ("gte", 6, []),
        ]:
            response = api_client.get(
                "/v1/parkeervakken/parkeervakken/",
                data={f"aantal[{op}]": str(filter_aantal)},
            )
            data = read_response_json(response)["_embedded"]["parkeervakken"]
            assert len(data) == len(expect)
            assert {x["id"] for x in data} == {x.id for x in expect}

    @staticmethod
    def test_geofilter_contains(api_client, parkeervakken_parkeervak_model, filled_router):
        """
        Prove that geofilter contains filters work as expected.
        """
        parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
            geometry=GEOSGeometry(
                "POLYGON((121140.66 489048.21, 121140.72 489047.1, 121140.8 489046.9, 121140.94 "
                "489046.74,121141.11 489046.62, 121141.31 489046.55, 121141.52 489046.53, "
                "121134.67 489045.85, 121134.47 489047.87, 121140.66 489048.21))",
                28992,
            ),
        )

        # Inside using RD
        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "121137.7,489046.9"},
            HTTP_ACCEPT_CRS=28992,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1, "inside with R/D"

        # Inside using WGS84
        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,4.8897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert len(data["_embedded"]["parkeervakken"]) == 1, "inside with WGS84"

        # Outside using WGS84
        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.3883019,4.8900356"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 0, "Outside using WGS84"

        # Invalid WGS84 coords
        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,48897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        assert response.status_code == 400, "Outside WGS84 range"

    @staticmethod
    def test_filter_isempty(api_client, parkeervakken_parkeervak_model, filled_router):
        """ "Prove that the [isempty] operator works"""
        parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_parkeervak_model.objects.create(
            id="121138489007",
            type="File",
            soort="",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_parkeervak_model.objects.create(
            id="121138489008",
            type="File",
            soort=None,
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "true"},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 2
        assert (
            data["_embedded"]["parkeervakken"][0]["id"] == "121138489007"
            or data["_embedded"]["parkeervakken"][0]["id"] == "121138489008"
        )

        response = api_client.get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "false"},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1
        assert data["_embedded"]["parkeervakken"][0]["id"] == "121138489006"

    @staticmethod
    @pytest.mark.parametrize(
        "query",
        [
            {"actors.name": "John Doe"},
            {"actors.name[like]": "J*"},
        ],
    )
    def test_filter_m2m_results(api_client, movies_data_with_actors, filled_router, query):
        """Prove that filtering M2M models still return the objects just once."""
        response = api_client.get("/v1/movies/movie/", data=query)
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "movie": [
                {
                    "_links": {
                        "schema": (
                            "https://schemas.data.amsterdam.nl/datasets/movies/dataset#movie"
                        ),
                        "self": {
                            "href": "http://testserver/v1/movies/movie/3/",
                            "id": 3,
                            "title": "foo123",
                        },
                        "actors": [
                            # Both shown, even if filtered on existence of one.
                            {
                                "href": "http://testserver/v1/movies/actor/1/",
                                "id": "1",
                                "title": "John Doe",
                            },
                            {
                                "href": "http://testserver/v1/movies/actor/2/",
                                "id": "2",
                                "title": "Jane Doe",
                            },
                        ],
                        "category": {
                            "href": "http://testserver/v1/movies/category/1/",
                            "id": 1,
                            "title": "bar",
                        },
                    },
                    "categoryId": 1,
                    "dateAdded": "2020-01-01T00:45:00",
                    "enjoyable": None,
                    "id": 3,
                    "name": "foo123",
                    "url": None,
                }
            ]
        }

    @staticmethod
    @pytest.mark.parametrize(
        "query",
        [
            "movies.name=foo123",
            "movies.id[in]=3,4",
            "movies.name[not]=many",
        ],
    )
    def test_filter_reverse_fk(api_client, movies_data_with_actors, filled_router, query):
        """Prove that filtering reverse FK models works and returns the objects just once."""
        response = api_client.get(f"/v1/movies/category/?{query}")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert set(data["_embedded"].keys()) == {"category"}, data
        assert len(data["_embedded"]["category"]) == 1, data

    @staticmethod
    def test_filter_reverse_m2m(api_client, movies_data_with_actors, filled_router):
        """Prove that filtering M2M models works and returns the objects just once."""
        response = api_client.get("/v1/movies/actor/?movies.name=foo123")
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert set(data["_embedded"].keys()) == {"actor"}, data
        assert len(data["_embedded"]["actor"]) == 2, data
        names = [a["name"] for a in data["_embedded"]["actor"]]
        assert names == ["John Doe", "Jane Doe"]

    @pytest.mark.django_db
    def test_temporal_relation_isnull(self, api_client, huishoudelijkafval_data, filled_router):
        """isnull on a relation should check whether a relation exists at all,
        not check that a relation exists with a null identifier.
        """
        response = api_client.get(
            "/v1/huishoudelijkafval/cluster/?bagNummeraanduiding.identificatie[isnull]=true"
        )
        assert response.status_code == 200
        data = read_response_json(response)

        assert len(data["_embedded"]["cluster"]) > 0
