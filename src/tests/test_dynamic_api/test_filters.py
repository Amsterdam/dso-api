import pytest
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APIClient

from dso_api.dynamic_api.filterset import filterset_factory
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
    def test_additional_filters(
        parkeervakken_parkeervak_model, parkeervakken_regime_model, filled_router
    ):
        """
        Prove that additional filters work as expected.

        Setup is a little explicit, contains:
         - 1 parkeervak with eType E6b between 8:00 and 10:00
         - 1 parkeervak with no special mode
         - 1 parkeervak with eType E7 between 8:00 and 10:00

        Request with: regimes.eType=E6b&regimes.inWerkingOp=08:00
        should yield only first parkeervak.
        """

        parkeervak = parkeervakken_parkeervak_model.objects.create(
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
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begintijd="00:00:00",
            eindtijd="07:59:00",
            einddatum=None,
            begindatum=None,
        )
        parkeervakken_regime_model.objects.create(
            id=3,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="",
            opmerking="",
            begintijd="08:00:00",
            eindtijd="09:59:00",
            einddatum=None,
            begindatum=None,
        )

        parkeervakken_regime_model.objects.create(
            id=4,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begintijd="10:00:00",
            eindtijd="23:59:00",
            einddatum=None,
            begindatum=None,
        )

        extra_parkeervak = parkeervakken_parkeervak_model.objects.create(
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
            parent=extra_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begintijd="00:00:00",
            eindtijd="23:59:00",
            einddatum=None,
            begindatum=None,
        )

        exclude_parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489056",
            type="File",
            soort="FISCAAL",
            aantal=1.0,
            e_type="",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=5,
            parent=exclude_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="FISCAAL",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begintijd="00:00:00",
            eindtijd="07:59:00",
            einddatum=None,
            begindatum=None,
        )
        parkeervakken_regime_model.objects.create(
            id=6,
            parent=exclude_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E7",
            kenteken="",
            opmerking="",
            begintijd="08:00:00",
            eindtijd="09:59:00",
            einddatum=None,
            begindatum=None,
        )

        parkeervakken_regime_model.objects.create(
            id=7,
            parent=exclude_parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="FISCAAL",
            aantal=None,
            e_type="",
            kenteken="",
            opmerking="",
            begintijd="10:00:00",
            eindtijd="23:59:00",
            einddatum=None,
            begindatum=None,
        )

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "08:00", "regimes.eType": "E6b"},
        )
        data = read_response_json(response)

        assert len(data["_embedded"]["parkeervakken"]) == 1, data
        assert data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(data["_embedded"]["parkeervakken"][0]["regimes"]) == 3, data

    @staticmethod
    def test_additional_filters_with_null_start_value(
        parkeervakken_parkeervak_model, parkeervakken_regime_model, filled_router
    ):
        """
        Prove that additional filters work as expected.

        Setup contains:
         - 1 parkeervak with eType E6b between no start time and 10:00

        Request with: regimes.eType=E6b&regimes.inWerkingOp=09:00
        should yield parkeervak.
        """

        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )

        parkeervakken_regime_model.objects.create(
            id=6,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="",
            opmerking="",
            begintijd=None,
            eindtijd="10:00:00",
            einddatum=None,
            begindatum=None,
        )

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "09:00", "regimes.eType": "E6b"},
        )
        data = read_response_json(response)

        assert len(data["_embedded"]["parkeervakken"]) == 1, data
        assert data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(data["_embedded"]["parkeervakken"][0]["regimes"]) == 1, data

    @staticmethod
    def test_additional_filters_with_null_end_value(
        parkeervakken_parkeervak_model, parkeervakken_regime_model, filled_router
    ):
        """
        Prove that additional filters work as expected.

        Setup contains:
         - 1 parkeervak with eType E6b between 8:00 and no end time

        Request with: regimes.eType=E6b&regimes.inWerkingOp=09:00
        should yield parkeervak.
        """

        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489006",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E6b",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )

        parkeervakken_regime_model.objects.create(
            id=6,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="",
            opmerking="",
            begintijd="08:00:00",
            eindtijd=None,
            einddatum=None,
            begindatum=None,
        )

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "09:00", "regimes.eType": "E6b"},
        )
        data = read_response_json(response)

        assert len(data["_embedded"]["parkeervakken"]) == 1, data
        assert data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(data["_embedded"]["parkeervakken"][0]["regimes"]) == 1, data

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
            headers={"Accept-CRS": 4326},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.3883019,4.8900356"},
            headers={"Accept-CRS": 4326},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 0

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "121137.7,489046.9"},
            headers={"Accept-CRS": 28992},
        )
        data = read_response_json(response)
        assert len(data["_embedded"]["parkeervakken"]) == 1

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,48897865"},
            headers={"Accept-CRS": 4326},
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

        assert expected_fields.issubset(
            [(k, v.field_name) for k, v in filterset_class.get_filters().items()]
        )

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
