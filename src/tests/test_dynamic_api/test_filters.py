import math

import pytest
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.exceptions import ValidationError
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.test import APIClient

from dso_api.dynamic_api.filterset import filterset_factory
from rest_framework_dso.filters.backends import _parse_point, _validate_convert_x_y
from tests.utils import read_response_json


@pytest.mark.django_db
class TestDynamicFilterSet:
    @staticmethod
    def test_serializer_has_nested_table(
        parkeervakken_parkeervak_model, parkeervakken_regime_model
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

        filterset_class = filterset_factory(Parkeervakken)
        filterset = filterset_class({"regimes.eType": "E6b"})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(Parkeervakken.objects.all())
        assert result.count() == 1, result

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

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,4.8897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.3883019,4.8900356"},
            HTTP_ACCEPT_CRS=4326,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 0

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "121137.7,489046.9"},
            HTTP_ACCEPT_CRS=28992,
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,48897865"},
            HTTP_ACCEPT_CRS=4326,
        )
        assert response.status_code == 400

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

    @staticmethod
    def test_subobject_filters(verblijfsobjecten_model, verblijfsobjecten_data):
        VerblijfsObjecten = verblijfsobjecten_model
        filterset_class = filterset_factory(VerblijfsObjecten)

        # dotted filters are generated on the FK subobjects only
        expected_fields = {
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
        }

        actual_fields = set(
            (k, v.field_name) for k, v in filterset_class.get_filters().items() if "." in k
        )
        assert expected_fields.issubset(actual_fields)

        assert VerblijfsObjecten.objects.count() == 4

        filterset = filterset_class({"heeftHoofdadres.volgnummer": 1})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(VerblijfsObjecten.objects.all())
        assert result.count() == 2, result

        filterset = filterset_class({"heeftHoofdadres.identificatie": "nm2"})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(VerblijfsObjecten.objects.all())
        assert result.count() == 1, result

        filterset = filterset_class({"ligtInBuurt.identificatie[isnull]": True})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(VerblijfsObjecten.objects.all())
        assert result.count() == 0, result

        filterset = filterset_class({"ligtInBuurt.volgnummer[gte]": 2})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(VerblijfsObjecten.objects.all())
        assert result.count() == 3, result

        filterset = filterset_class({"ligtInBuurt.identificatie[like]": "X*X"})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(VerblijfsObjecten.objects.all())
        assert result.count() == 1, result


@pytest.mark.parametrize(
    "value",
    [
        "0,0",
        "-1,-0.69315",
        "5,52",
        "52.1,1",
        "POINT(0.0 0.0)",
        "POINT(-1.1 -3.3)",
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
    ["", "a", "foo", "0, 0", "inf,nan", "0," + 314 * "1"]
    + ["POINT", "POINT ", "POINT(x y)", "POINT(1.0 2.0", "POINT(1.0,2.0)", "POINT 1.0 2.0"]
    + ["POINT(0 0)", "POINT(1. .1)", "POINT(-1 2)"],  # XXX allow these?
)
def test_parse_input_invalid(value):
    try:
        _parse_point(value)
    except ValidationError as e:  # Triggers error 400 Bad Request.
        assert repr(value) in str(e)
    else:
        raise Exception(f"no exception for {value!r}")


@pytest.mark.parametrize(
    "x,y,srid,out",
    [
        (1, 400000, 28992, (1, 400000, 28992)),  # explicit RD coordinates
        (1, 400000, None, (1, 400000, 28992)),  # implicit RD coordinates
        (5, 52, None, (5, 52, 4326)),  # implicit SRID 4326
        (52, 5, None, (5, 52, 4326)),  # lat/lon may be swapped
        (1, 1, None, (None, None, None)),  # SRID cannot be determined
        # known SRID but invalid coordinates becomes (None, None, srid)
        (1, 400000, 4326, (None, None, 4326)),
        (0, 52, 4326, (None, None, 4326)),
        (1, 4, 28992, (None, None, 28992)),
        # unknown SRID always passed through
        (0, 1, 1234, (0, 1, 1234)),
        (-1, -2, -3, (-1, -2, -3)),
        (1, 400000, 999, (1, 400000, 999)),
    ],
)
def test_validate_convert_x_y(x, y, srid, out):
    assert _validate_convert_x_y(x, y, srid) == out
