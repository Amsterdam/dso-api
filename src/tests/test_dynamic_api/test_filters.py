import pytest
from django.apps import apps
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.test import APIClient

from dso_api.dynamic_api.filterset import filterset_factory


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
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None,
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
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None,
        )

        filterset_class = filterset_factory(Parkeervakken)
        filterset = filterset_class({"regimes.eType": "E6b"})
        assert filterset.is_valid(), filterset.errors

        result = filterset.filter_queryset(Parkeervakken.objects.all())
        assert result.count() == 1, result

    @staticmethod
    def test_additional_filters(parkeervakken_parkeervak_model, parkeervakken_regime_model):
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
            begin_tijd="00:00:00",
            eind_tijd="07:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="08:00:00",
            eind_tijd="09:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="10:00:00",
            eind_tijd="23:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="00:00:00",
            eind_tijd="23:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="00:00:00",
            eind_tijd="07:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="08:00:00",
            eind_tijd="09:59:00",
            eind_datum=None,
            begin_datum=None,
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
            begin_tijd="10:00:00",
            eind_tijd="23:59:00",
            eind_datum=None,
            begin_datum=None,
        )

        # Router reload is needed to make sure that viewsets are using relations.
        from dso_api.dynamic_api.urls import router

        router.reload()
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "08:00", "regimes.eType": "E6b"},
        )

        assert len(response.data["_embedded"]["parkeervakken"]) == 1, response.data
        assert response.data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(response.data["_embedded"]["parkeervakken"][0]["regimes"]) == 3, response.data

    @staticmethod
    def test_additional_filters_with_null_start_value(
        parkeervakken_parkeervak_model, parkeervakken_regime_model
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
            begin_tijd=None,
            eind_tijd="10:00:00",
            eind_datum=None,
            begin_datum=None,
        )

        # Router reload is needed to make sure that viewsets are using relations.
        from dso_api.dynamic_api.urls import router

        router.reload()
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "09:00", "regimes.eType": "E6b"},
        )

        assert len(response.data["_embedded"]["parkeervakken"]) == 1, response.data
        assert response.data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(response.data["_embedded"]["parkeervakken"][0]["regimes"]) == 1, response.data

    @staticmethod
    def test_additional_filters_with_null_end_value(
        parkeervakken_parkeervak_model, parkeervakken_regime_model
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
            begin_tijd="08:00:00",
            eind_tijd=None,
            eind_datum=None,
            begin_datum=None,
        )

        # Router reload is needed to make sure that viewsets are using relations.
        from dso_api.dynamic_api.urls import router

        router.reload()
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"regimes.inWerkingOp": "09:00", "regimes.eType": "E6b"},
        )

        assert len(response.data["_embedded"]["parkeervakken"]) == 1, response.data
        assert response.data["_embedded"]["parkeervakken"][0]["id"] == parkeervak.pk
        assert len(response.data["_embedded"]["parkeervakken"][0]["regimes"]) == 1, response.data

    @staticmethod
    def test_geofilter_contains(parkeervakken_parkeervak_model):
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

        from dso_api.dynamic_api.urls import router

        router.reload()
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.388231,4.8897865"},
            headers={"Accept-CRS": 4326},
        )
        assert len(response.data["_embedded"]["parkeervakken"]) == 1

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "52.3883019,4.8900356"},
            headers={"Accept-CRS": 4326},
        )
        assert len(response.data["_embedded"]["parkeervakken"]) == 0

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"geometry[contains]": "121137.7,489046.9"},
            headers={"Accept-CRS": 28992},
        )
        assert len(response.data["_embedded"]["parkeervakken"]) == 1

    @staticmethod
    def test_filter_isempty(parkeervakken_parkeervak_model):
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
        from dso_api.dynamic_api.urls import router

        router.reload()
        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "true"},
        )
        assert len(response.data["_embedded"]["parkeervakken"]) == 2
        assert (
            response.data["_embedded"]["parkeervakken"][0]["id"] == "121138489007"
            or response.data["_embedded"]["parkeervakken"][0]["id"] == "121138489008"
        )

        response = APIClient().get(
            "/v1/parkeervakken/parkeervakken/",
            data={"soort[isempty]": "false"},
        )
        assert len(response.data["_embedded"]["parkeervakken"]) == 1
        assert response.data["_embedded"]["parkeervakken"][0]["id"] == "121138489006"
