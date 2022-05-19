from __future__ import annotations

import math
from datetime import date

import pytest
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from django.http import QueryDict
from rest_framework.exceptions import ValidationError
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.test import APIClient
from schematools.contrib.django.models import Dataset
from schematools.permissions import UserScopes

from dso_api.dynamic_api.filters import parser
from dso_api.dynamic_api.filters.lookups import _sql_wildcards
from dso_api.dynamic_api.filters.values import _parse_point, _validate_correct_x_y, str2geo
from rest_framework_dso.crs import RD_NEW
from tests.utils import read_response_json


class TestWildcard:
    @pytest.mark.django_db
    def test_like_filter_sql(self, django_assert_num_queries):
        with django_assert_num_queries(1) as context:
            # using str(qs.query) doesn't apply database-level escaping,
            # so running the query instead to get the actual executed query.
            list(Dataset.objects.filter(name__like="foo*bar?"))

        sql = context.captured_queries[0]["sql"]
        assert r"""."name" LIKE 'foo%bar_'""" in sql


def test_sql_wildcards():
    assert _sql_wildcards("foo*") == "foo%"
    assert _sql_wildcards("fo?o") == r"fo_o"
    assert _sql_wildcards("fo%o") == r"fo\%o"
    assert _sql_wildcards("fo%o_") == r"fo\%o\_"
    assert _sql_wildcards("f?_oob%ar*") == r"f_\_oob\%ar%"


def create_filter_engine(query_string: str, request_scopes=()) -> parser.QueryFilterEngine:
    """Simulate creation of a filter engine, based on request data."""
    get_params = QueryDict(query_string)
    return parser.QueryFilterEngine(
        UserScopes(get_params, request_scopes), get_params, input_crs=RD_NEW
    )


@pytest.mark.django_db
class TestFilterEngine:
    """Test the individual parts of the filter engine."""

    @pytest.fixture
    def movie1(self, movies_model, movies_category):
        return movies_model.objects.create(
            name="movie1", category=movies_category, date_added=date(2020, 2, 1)
        )

    @pytest.fixture
    def movie2(self, movies_model, movies_category):
        return movies_model.objects.create(
            name="movie2", date_added=date(2020, 3, 1), url="http://example.com/someurl"
        )

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "query,expect",
        [
            # Date less than
            ("dateAdded[lt]=2020-2-10", {"movie1"}),
            ("dateAdded[lt]=2020-3-1", {"movie1"}),
            ("dateAdded[lte]=2020-3-1", {"movie1", "movie2"}),
            # Date less than full datetime
            ("dateAdded[lt]=2020-3-1T23:00:00", {"movie1", "movie2"}),
            # Date greater than
            ("dateAdded[gt]=2020-2-10", {"movie2"}),
            ("dateAdded[gt]=2020-3-1", set()),
            ("dateAdded[gte]=2020-3-1", {"movie2"}),
            # Not (can be repeated for "AND NOT" testing)
            ("dateAdded[not]=2020-2-1", {"movie2"}),
            ("dateAdded[not]=2020-2-1&dateAdded[not]=2020-3-1", set()),
            # URLs have string-like comparison operators
            ("url[like]=http:*", {"movie2"}),
            ("url[isnull]=true", {"movie1"}),
        ],
    )
    def test_filter_logic(self, movies_model, movie1, movie2, query, expect):
        engine = create_filter_engine(query)
        qs = engine.filter_queryset(movies_model.objects.all())
        assert {obj.name for obj in qs} == expect, str(qs.query)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "query,expect",
        [
            # IN filter
            ("category.id[in]={cat_id}", {"movie1"}),  # test ID
            ("category.id[in]={cat_id},{cat_id}", {"movie1"}),  # test comma
            ("category.id[in]=97,98,{cat_id}", {"movie1"}),  # test invalid IDs
            ("category.id[in]=97,98,99", set()),  # test all invalid IDs
            # NOT filter
            ("category.id[not]={cat_id}", {"movie2"}),
            ("category.id[not]=99", {"movie1", "movie2"}),
            # Old deprecated notation:
            ("categoryId[in]={cat_id}", {"movie1"}),
            ("categoryId[not]=99", {"movie1", "movie2"}),
        ],
    )
    def test_foreignkey(self, movies_model, movie1, movie2, category, query, expect):
        # Replace {cat_id} in values:
        query = query.format(cat_id=category.pk)
        engine = create_filter_engine(query)
        qs = engine.filter_queryset(movies_model.objects.all())
        assert {obj.name for obj in qs} == expect, str(qs.query)

    @staticmethod
    def test_filter_nested_table(
        parkeervakken_dataset, parkeervakken_parkeervak_model, parkeervakken_regime_model
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        # reload model from APPs registry, in ordeer to fetch all relations.
        Parkeervakken = apps.get_model("parkeervakken", "parkeervakken")
        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489047",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
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
            e_type="E9",
            kenteken="69-SF-NT",
            opmerking="",
            eindtijd="23:59:00",
            begintijd="00:00:00",
            einddatum=None,
            begindatum=None,
        )
        other_parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=2,
            parent=other_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="69-SF-NT",
            opmerking="",
            eindtijd="23:59:00",
            begintijd="00:00:00",
            einddatum=None,
            begindatum=None,
        )

        engine = create_filter_engine("regimes.eType=E6b")
        result = engine.filter_queryset(Parkeervakken.objects.all())
        assert result.count() == 1, result

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 1),
            ("ligtInBouwblok.identificatie=03630012096483&ligtInBouwblok.volgnummer=1", 1),
            ("ligtInBouwblok.identificatie=03630012096483&ligtInBouwblok.volgnummer=2", 0),
            ("ligtInBouwblokId=03630012096483.1", 1),  # deprecated format, but test anyway!
            ("ligtInBouwblokId=123", 0),
            ("ligtInBouwblok.ligtInBuurtId=03630000000078.2", 1),
            ("ligtInBouwblok.ligtInBuurt.identificatie=03630000000078", 1),
        ],
    )
    def test_filter_temporal(bag_dataset, panden_model, panden_data, query, expect):
        """Test that filtering on temporal relations works.
        This checks both the dotted-notation, and the old 'compositeKeyId' FK field.
        """
        engine = create_filter_engine(query)
        result = engine.filter_queryset(panden_model.objects.all())
        assert result.count() == expect, result

    @staticmethod
    def test_subobject_parsing(bag_dataset):
        verblijfsobjecten_schema = bag_dataset.schema.get_table_by_id("verblijfsobjecten")
        expected_fields = [
            ("heeftHoofdadres.volgnummer", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[gt]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[gte]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[in]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[isnull]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[lt]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[lte]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.volgnummer[not]", "heeft_hoofdadres_volgnummer"),
            ("heeftHoofdadres.identificatie", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[isempty]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[isnull]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[like]", "heeft_hoofdadres_identificatie"),
            ("heeftHoofdadres.identificatie[not]", "heeft_hoofdadres_identificatie"),
            ("ligtInBuurt.identificatie", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[isempty]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[isnull]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[like]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.identificatie[not]", "ligt_in_buurt_identificatie"),
            ("ligtInBuurt.volgnummer", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[gt]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[gte]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[in]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[isnull]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[lt]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[lte]", "ligt_in_buurt_volgnummer"),
            ("ligtInBuurt.volgnummer[not]", "ligt_in_buurt_volgnummer"),
        ]

        scopes = UserScopes({}, [])
        for query_key, orm_path in expected_fields:
            filter_input = parser.FilterInput.from_parameter(query_key, raw_values=[])
            fields = parser.parse_filter_path(filter_input.path, verblijfsobjecten_schema, scopes)
            assert parser._to_orm_path(fields) == orm_path

    @staticmethod
    @pytest.mark.parametrize(
        "query,expect",
        [
            ("", 4),
            ("heeftHoofdadres.volgnummer=1", 2),
            ("heeftHoofdadres.identificatie=nm2", 1),
            ("ligtInBuurt.identificatie[isnull]=1", 0),
            ("ligtInBuurt.volgnummer[gte]=2", 3),
            ("ligtInBuurt.identificatie[like]=X*X", 1),
        ],
    )
    def test_subobject_filters(verblijfsobjecten_model, verblijfsobjecten_data, query, expect):
        # dotted filters are generated on the FK subobjects only
        engine = create_filter_engine(query)
        result = engine.filter_queryset(verblijfsobjecten_model.objects.all())
        assert result.count() == expect, result


@pytest.mark.django_db
class TestDynamicFilterSet:
    """Test how the filters work using the API client and views."""

    @staticmethod
    def test_numerical_filters(parkeervakken_parkeervak_model, filled_router):
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
            response = APIClient().get(
                "/v1/parkeervakken/parkeervakken/",
                data={f"aantal[{op}]": str(filter_aantal)},
            )
            data = read_response_json(response)["_embedded"]["parkeervakken"]
            assert len(data) == len(expect)
            assert {x["id"] for x in data} == {x.id for x in expect}

    @staticmethod
    def test_geofilter_contains(parkeervakken_parkeervak_model, filled_router):
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
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "121137.7,489046.9"},
            HTTP_ACCEPT_CRS=28992,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1, "inside with R/D"

        # Inside using WGS84
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,4.8897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert len(data["_embedded"]["parkeervakken"]) == 1, "inside with WGS84"

        # Outside using WGS84
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.3883019,4.8900356"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 0, "Outside using WGS84"

        # Invalid WGS84 coords
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,48897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        assert response.status_code == 400, "Outside WGS84 range"

    @staticmethod
    def test_filter_isempty(parkeervakken_parkeervak_model, filled_router):
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
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "true"},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 2
        assert (
            data["_embedded"]["parkeervakken"][0]["id"] == "121138489007"
            or data["_embedded"]["parkeervakken"][0]["id"] == "121138489008"
        )

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "false"},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1
        assert data["_embedded"]["parkeervakken"][0]["id"] == "121138489006"

    @staticmethod
    @pytest.mark.parametrize("params", [{"e_type": "whatever"}, {"_sort": "e_type"}])
    def test_snake_case_400(params, parkeervakken_parkeervak_model):
        """Filter names match property names in the schema.
        We no longer accept snake-cased property names."""
        response = APIClient().get("/v1/parkeervakken/parkeervakken/", data=params)
        assert response.status_code == HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "value",
    [
        "0,0",
        "-1,-0.69315",
        "5,52",
        "52.1,1",
        "POINT(0 0)",
        "POINT(0.0 0.0)",
        "POINT(-1.1 -3.3)",
        "POINT(-1 2)",
        "POINT(100.0 42.0)",
    ],
)
def test_parse_point(value):
    x, y = _parse_point(value)
    assert isinstance(x, float)
    assert isinstance(y, float)
    assert math.isfinite(x)
    assert math.isfinite(y)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a",
        "foo",
        "inf,nan",
        "0, 0",
        "0," + 314 * "1",
        "POINT",
        "POINT ",
        "POINT(x y)",
        "POINT(1.0 2.0",
        "POINT(1.0,2.0)",
        "POINT 1.0 2.0",
        "POINT(1. .1)",
    ],
)
def test_parse_point_invalid(value):
    with pytest.raises(ValidationError):
        _parse_point(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a",
        "foo",
        "inf,nan",
        "0, 0",
        "0," + 314 * "1",
        "POINT",
        "POINT ",
        "POINT(x y)",
        "POINT(1.0 2.0",
        "POINT(1.0,2.0)",
        "POINT 1.0 2.0",
        "POINT(1. .1)",
        # Outside range of Netherlands:
        "POINT(0 0)",
        "POINT(0.0 0.0)",
        "POINT(-1.1 -3.3)",
        "POINT(-1 2)",
        "POINT(100.0 42.0)",
    ],
)
def test_str2geo_invalid(value):
    with pytest.raises(ValidationError) as exc_info:
        str2geo(value)

    assert repr(value) in str(exc_info.value)


@pytest.mark.parametrize(
    "x,y,srid,out",
    [
        (1, 400000, 28992, (1, 400000, 28992)),  # explicit RD coordinates
        (1, 400000, None, (1, 400000, 28992)),  # implicit RD coordinates
        (5, 52, None, (5, 52, 4326)),  # implicit SRID 4326
        (52, 5, None, (5, 52, 4326)),  # lat/lon may be swapped
        # unknown SRID always passed through
        (0, 1, 1234, (0, 1, 1234)),
        (-1, -2, -3, (-1, -2, -3)),
        (1, 400000, 999, (1, 400000, 999)),
    ],
)
def test_validate_convert_x_y(x, y, srid, out):
    point = _validate_correct_x_y(x, y, srid)
    assert point.x == out[0]
    assert point.y == out[1]
    assert point.srid == out[2]


@pytest.mark.parametrize(
    "x,y,srid,out",
    [
        (1, 1, None, (None, None, None)),  # SRID cannot be determined
        # known SRID but invalid coordinates becomes (None, None, srid)
        (1, 400000, 4326, (None, None, 4326)),
        (0, 52, 4326, (None, None, 4326)),
        (1, 4, 28992, (None, None, 28992)),
    ],
)
def test_validate_convert_x_y_exception(x, y, srid, out):
    with pytest.raises(ValueError) as exc_info:
        _validate_correct_x_y(x, y, srid)

    assert "Invalid x,y values" in str(exc_info.value)
