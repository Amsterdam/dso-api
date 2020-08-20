from datetime import date, datetime
import pytest
from django.urls import reverse


@pytest.fixture()
def bagh_stadsdeelen(bagh_models):
    """
    Creates Gemeente Amsterdaam and Stadsdeel Zuidoost.
    """
    Gemeente = bagh_models["gemeente"]
    Stadsdeel = bagh_models["stadsdeel"]
    gemeente = Gemeente.objects.create(
        pk="0363_001",
        identificatie="0363",
        volgnummer=1,
        registratiedatum=datetime(1899, 1, 1, 18, 0, 0),
        begin_geldigheid=date(1900, 1, 1),
        eind_geldigheid=None,
        naam="Amsterdam",
        verzorgingsgebied=True,
    )
    stadsdeel = Stadsdeel.objects.create(
        id="03630000000016_001",
        identificatie="03630000000016",
        volgnummer=1,
        registratiedatum=datetime(2006, 6, 12, 5, 40, 12),
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
        gemeente=gemeente,
    )

    stadsdeel_v2 = Stadsdeel.objects.create(
        id="03630000000016_002",
        identificatie="03630000000016",
        volgnummer=2,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12),
        begin_geldigheid=date(2015, 1, 1),
        eind_geldigheid=None,
        naam="Zuidoost",
        gemeente=gemeente,
    )
    return [stadsdeel, stadsdeel_v2]


@pytest.fixture()
def bagh_wijk_1(bagh_models, bagh_stadsdeelen):
    """
    Creates gebied that is connected to Stadsdeel Zuidoost.
    """
    Wijk = bagh_models["wijk"]
    return Wijk.objects.create(
        id="03630950000019_001",
        identificatie="03630950000019",
        volgnummer=1,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12),
        begin_geldigheid=date(2014, 2, 20),
        naam="Bijlmer-Centrum",
        stadsdeel=bagh_stadsdeelen[1],
    )


@pytest.mark.django_db
class TestViews:
    def test_list_contains_all_objects(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that default API response contains ALL versions."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get(url)

        assert response.status_code == 200, response.data
        assert len(response.data["_embedded"]["stadsdeel"]) == 2, response.data[
            "_embedded"
        ]["stadsdeel"]

    def test_filtered_list_contains_only_correct_objects(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that date filter displays only active on that date objects.."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get(f"{url}?geldigOp=2015-01-02")

        assert response.status_code == 200, response.data
        assert len(response.data["_embedded"]["stadsdeel"]) == 1, response.data[
            "_embedded"
        ]["stadsdeel"]
        assert (
            response.data["_embedded"]["stadsdeel"][0]["volgnummer"] == 2
        ), response.data["_embedded"]["stadsdeel"][0]

    def tets_details_record_can_be_requested_by_pk(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that request with PK (combined field) is allowed."""
        url = reverse("dynamic_api:bagh-stadsdeel-detail", bagh_stadsdeelen[0].id)
        response = api_client.get(url)

        assert response.status_code == 200, response.data
        assert (
            response.data["volgnummer"] == bagh_stadsdeelen[0].volgnummer
        ), response.data

    def test_details_default_returns_latest_record(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that object can be requested by identification
        and response will contain only latest object."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get(
            "{}{}/".format(url, bagh_stadsdeelen[0].identificatie)
        )

        assert response.status_code == 200, response.data
        assert response.data["volgnummer"] == 2, response.data

    def test_details_can_be_requested_with_valid_date(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that object can be requested by identification and date,
        resulting in correct for that date object."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get(
            "{}{}/?geldigOp=2014-12-12".format(url, bagh_stadsdeelen[0].identificatie)
        )

        assert response.status_code == 200, response.data
        assert response.data["volgnummer"] == 1, response.data

    def test_details_can_be_requested_with_version(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that object can be requested by identification and version,
        resulting in correct for that version object."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get(
            "{}{}/?volgnummer=1".format(url, bagh_stadsdeelen[0].identificatie)
        )

        assert response.status_code == 200, response.data
        assert response.data["volgnummer"] == 1, response.data

    def test_serializer_contains_correct_id_for_gemeente(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen
    ):
        """ Prove that serializer contains identification of gemeente and not combined ID."""
        url = reverse("dynamic_api:bagh-stadsdeel-list")
        response = api_client.get("{}{}/".format(url, bagh_stadsdeelen[0].id))

        assert (
            response.data["gemeenteId"] == bagh_stadsdeelen[0].gemeente.identificatie
        ), response.data

    def test_serializer_contains_correct_link_to_stadsdeel(
        self, api_client, filled_router, bagh_schema, bagh_stadsdeelen, ggwgebieden_model
    ):
        """ Prove that serializer contains link to correct version of stadsdeel."""

        test_gebied = ggwgebieden_model.objects.create(
            identificatie='010001',
            volgnummer=1,
            naam='De Test',
            ligtinstadsdeel=bagh_stadsdeelen[0],
        )
        url = reverse("dynamic_api:gebieden-ggwgebied-list")
        response = api_client.get("{}{}/".format(url, test_gebied.identificatie))

        expected_url = "/{}/?volgnummer={}".format(
            test_gebied.ligtinstadsdeel.identificatie,
            str(test_gebied.ligtinstadsdeel.volgnummer).zfill(3)
        )
        assert str(response.data["ligtinstadsdeel"]).endswith(expected_url), response.data[
            "ligtinstadsdeel"
        ]

    def test_serializer_temporal_request_corrects_link_to_temporal(
        self, api_client, filled_router, bagh_schema, bagh_wijk_1
    ):
        """ Prove that in case of temporal request links to objects will have request date.
        Allowing follow up date filtering further."""
        url = reverse("dynamic_api:bagh-wijk-list")
        response = api_client.get(
            "{}{}/?geldigOp=2014-05-01".format(url, bagh_wijk_1.identificatie)
        )

        expected_url = "/{}/?geldigOp=2014-05-01".format(
            bagh_wijk_1.stadsdeel.identificatie
        )
        assert response.data["stadsdeel"].endswith(expected_url), response.data[
            "stadsdeel"
        ]
