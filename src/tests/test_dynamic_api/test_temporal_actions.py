from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

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
        id="11", ggwgebieden_id="03630950000019.1", bestaat_uit_buurten_id="03630000000078.1"
    )
    return gebied


@pytest.fixture()
def buurt(gebieden_models, stadsdelen, wijk):
    Buurt = gebieden_models["buurten"]
    return Buurt.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        begin_geldigheid=date(2014, 2, 20),
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
class TestTemporalViews:
    def test_list_all_objects(self, api_client, stadsdelen):
        """Prove that API response can return ALL versions if requested."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url, {"geldigOp": "*"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        stadsdelen = data["_embedded"]["stadsdelen"]
        assert len(stadsdelen) == 2, stadsdelen
        assert stadsdelen[0]["_links"]["self"]["volgnummer"] == 1, stadsdelen[0]
        assert stadsdelen[1]["_links"]["self"]["volgnummer"] == 2, stadsdelen[1]

    def test_list_default_active_objects(self, api_client, stadsdelen):
        """Prove that default API response contains only active versions."""
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url)
        data = read_response_json(response)

        assert response.status_code == 200, data
        stadsdelen = data["_embedded"]["stadsdelen"]
        assert len(stadsdelen) == 1, stadsdelen
        assert stadsdelen[0]["_links"]["self"]["volgnummer"] == 2, stadsdelen[0]

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

        query_params = _parse_query_string(wijken[0]["_links"]["buurt"]["href"])
        assert query_params == {"geldigOp": ["2015-01-02"], "ligtInWijkId": ["03630012052022.1"]}

    def test_details_record_can_be_requested_by_pk(self, api_client, stadsdelen):
        """Prove that request with PK (combined field) is allowed.
        It still needs ?geldigOp=* or it will not find the "deleted" record.
        """
        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=(stadsdelen[0].id,))
        response = api_client.get(url, {"geldigOp": "*"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == stadsdelen[0].volgnummer, data

    def test_details_default_returns_latest_record(self, api_client, stadsdelen):
        """Prove that object can be requested by identification
        and response will contain only latest object."""
        identificatie = stadsdelen[0].identificatie
        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=(identificatie,))
        response = api_client.get(url)
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 2, data
        assert data["id"] == stadsdelen[1].id, data

    def test_details_can_be_requested_with_valid_date(self, api_client, stadsdelen):
        """Prove that object can be requested by identification and date."""
        identificatie = stadsdelen[0].identificatie
        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=(identificatie,))
        response = api_client.get(url, {"geldigOp": "2014-12-12"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 1, data

    def test_details_can_be_requested_with_version(self, api_client, stadsdelen):
        """Prove that object can be requested by identification and version."""
        identificatie = stadsdelen[0].identificatie
        url = reverse("dynamic_api:gebieden-stadsdelen-detail", args=(identificatie,))
        response = api_client.get(url, {"volgnummer": "1"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        assert data["_links"]["self"]["volgnummer"] == 1, response.data

    def test_serializer_temporal_request_corrects_link_to_temporal(
        self, api_client, gebied, buurt, filled_router
    ):
        """Prove that in case of temporal request links to objects will have request date.
        Allowing follow up date filtering further."""
        url = reverse("dynamic_api:gebieden-ggwgebieden-detail", args=(gebied.id,))
        response = api_client.get(url, {"geldigOp": "2014-05-01"})
        data = read_response_json(response)
        assert data["_links"]["bestaatUitBuurten"] == [
            {
                "href": (
                    "http://testserver/v1/gebieden/buurten/03630000000078/?geldigOp=2014-05-01"
                ),
                "identificatie": None,
                "title": "03630000000078.1",
                "volgnummer": None,
            }
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
        stadsdelen = data["_embedded"]["stadsdelen"]
        assert len(stadsdelen) == 1, stadsdelen
        assert _parse_query_string(stadsdelen[0]["_links"]["self"]["href"]) == {
            "_format": ["json"],
            "volgnummer": ["2"],
        }
        assert _parse_query_string(stadsdelen[0]["_links"]["wijken"][0]["href"]) == {
            "_format": ["json"],
            "volgnummer": ["1"],
        }


def _parse_query_string(url) -> dict[str, list[str]]:
    """Convert the query-string of an URL to a dict."""
    return parse_qs(urlparse(url).query)
