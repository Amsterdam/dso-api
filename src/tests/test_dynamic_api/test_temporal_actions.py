from datetime import date, datetime
from urllib import parse

import pytest
from django.urls import reverse

from tests.utils import read_response_json


@pytest.fixture()
def stadsdelen(gebieden_models):
    """
    Create Stadsdeel Zuidoost.
    """
    Stadsdeel = gebieden_models["stadsdelen"]
    stadsdeel = Stadsdeel.objects.create(
        id="03630000000016.1",
        identificatie="03630000000016",
        volgnummer=1,
        registratiedatum=datetime(2006, 6, 12, 5, 40, 12),
        begin_geldigheid=date(2006, 6, 1),
        eind_geldigheid=date(2015, 1, 1),
        naam="Zuidoost",
    )

    stadsdeel_v2 = Stadsdeel.objects.create(
        id="03630000000016.2",
        identificatie="03630000000016",
        volgnummer=2,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12),
        begin_geldigheid=date(2015, 1, 1),
        eind_geldigheid=None,
        naam="Zuidoost",
    )
    return [stadsdeel, stadsdeel_v2]


@pytest.fixture()
def gebied(gebieden_models, stadsdelen, buurt):
    """
    Creates gebied that is connected to Stadsdeel Zuidoost.
    """
    Gebied = gebieden_models["ggwgebieden"]
    gebied = Gebied.objects.create(
        id="03630950000019.1",
        identificatie="03630950000019",
        volgnummer=1,
        registratiedatum=datetime(2015, 1, 1, 5, 40, 12),
        begin_geldigheid=date(2014, 2, 20),
        naam="Bijlmer-Centrum",
    )
    Gebied.bestaat_uit_buurten.through.objects.create(
        ggwgebieden_id="03630950000019.1", bestaat_uit_buurten_id="03630000000078.1"
    )
    return gebied


@pytest.fixture()
def buurt(gebieden_models, stadsdelen, wijk):
    Buurt = gebieden_models["buurten"]
    return Buurt.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        code="A00a",
        naam="Kop Zeedijk",
        ligt_in_wijk=wijk,
    )


@pytest.fixture()
def wijk(gebieden_models, stadsdelen):
    Wijk = gebieden_models["wijken"]
    return Wijk.objects.create(
        id="03630012052022.1",
        identificatie="03630012052022",
        volgnummer=1,
        begin_geldigheid=date(2015, 1, 1),
        code="H36",
        naam="Sloterdijk",
        ligt_in_stadsdeel=stadsdelen[1],
    )


@pytest.mark.django_db
class TestViews:
    def test_list_contains_all_objects(self, api_client, stadsdelen):
        """ Prove that default API response contains ALL versions."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url)
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert len(data["_embedded"]["stadsdelen"]) == 2, data["_embedded"]["stadsdelen"]

    def test_filtered_list_contains_only_correct_objects(self, api_client, stadsdelen, buurt):
        """Prove that date filter displays only active-on-that-date objects."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(f"{url}?geldigOp=2015-01-02")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert len(data["_embedded"]["stadsdelen"]) == 1, data["_embedded"]["stadsdelen"]
        stadsdelen = data["_embedded"]["stadsdelen"]
        assert stadsdelen[0]["_links"]["self"]["volgnummer"] == 2, stadsdelen[0]

    def test_additionalrelations_works_and_has_temporary_param(
        self, api_client, stadsdelen, wijk, buurt, router
    ):
        """Prove that the "summary" additionalRelation shows up in the result and
        has a "geldigOp" link.
        """
        url = reverse("dynamic_api:gebieden-wijken-list")
        response = api_client.get(f"{url}?geldigOp=2015-01-02")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert len(data["_embedded"]["wijken"]) == 1, data["_embedded"]["wijken"]
        wijken = data["_embedded"]["wijken"]
        assert wijken[0]["_links"]["self"]["volgnummer"] == 1, wijken[0]
        assert wijken[0]["_links"]["buurt"]["count"] == 1
        query_params = parse.parse_qs(parse.urlparse(wijken[0]["_links"]["buurt"]["href"]).query)
        assert query_params["geldigOp"] == ["2015-01-02"]

    def test_details_record_can_be_requested_by_pk(self, api_client, stadsdelen):
        """ Prove that request with PK (combined field) is allowed."""
        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=(stadsdelen[0].id,))
        response = api_client.get(url)
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == stadsdelen[0].volgnummer, data

    def test_details_default_returns_latest_record(self, api_client, stadsdelen):
        """Prove that object can be requested by identification
        and response will contain only latest object."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(f"{url}{stadsdelen[0].identificatie}/")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 2, data

    def test_details_can_be_requested_with_valid_date(self, api_client, stadsdelen):
        """Prove that object can be requested by identification and date,
        resulting in correct for that date object."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(f"{url}{stadsdelen[0].identificatie}/?geldigOp=2014-12-12")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 1, data

    def test_details_can_be_requested_with_version(self, api_client, stadsdelen):
        """Prove that object can be requested by identification and version,
        resulting in correct for that version object."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(f"{url}{stadsdelen[0].identificatie}/?volgnummer=1")
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 1, response.data

    def test_serializer_temporal_request_corrects_link_to_temporal(
        self, api_client, gebied, buurt, filled_router
    ):
        """Prove that in case of temporal request links to objects will have request date.
        Allowing follow up date filtering further."""
        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        # response = api_client.get(url)
        response = api_client.get(f"{url}{gebied.id}/?geldigOp=2014-05-01")
        data = read_response_json(response)

        buurt = gebied.bestaat_uit_buurten.all()[0]
        expected_url = f"/{buurt.identificatie}/?geldigOp=2014-05-01"
        assert data["_links"]["bestaatUitBuurten"][0]["href"].endswith(expected_url), data[
            "bestaatUitBuurten"
        ]

    def test_correct_handling_of_extra_url_params(
        self, api_client, stadsdelen, buurt, filled_router
    ):
        """Prove that extra url parameters do not interfere with the existing
        url parameters for temporality."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(f"{url}?_format=json")
        data = read_response_json(response)

        # Check if there is only one '?' in the temporal urls
        fetch_query_keys = lambda url: set(parse.parse_qs(parse.urlparse(url).query).keys())
        assert fetch_query_keys(data["_embedded"]["stadsdelen"][1]["_links"]["self"]["href"]) == {
            "_format",
            "volgnummer",
        }
        assert fetch_query_keys(
            data["_embedded"]["stadsdelen"][1]["_links"]["wijk"][0]["href"]
        ) == {"_format", "volgnummer"}
