import json
from pathlib import Path
from typing import Any, NamedTuple, Union

import orjson
import pytest
import urllib3
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_403_FORBIDDEN
from schematools.contrib.django import models
from schematools.types import DatasetTableSchema, ProfileSchema
from urllib3_mock import Responses

from dso_api.dynamic_api.remote.clients import RemoteClient
from tests.utils import read_response, read_response_json

DEFAULT_RESPONSE = {
    "naam": {
        "voornamen": "Ria",
        "voorletters": "R.",
        "voorvoegsel": "van",
        "geslachtsnaam": "Amstel",
        "aanduidingNaamgebruik": "eigen",
    },
    "geboorte": {"datum": {"dag": 12, "jaar": 1942, "datum": "1942-08-12", "maand": 8}},
    "leeftijd": 77,
    "verblijfplaats": {
        "postcode": "8603XM",
        "huisnummer": "6",
        "straatnaam": "Anjelierstraat",
        "functieAdres": "woonadres",
        "gemeenteVanInschrijving": {
            "code": "1900",
            "omschrijving": "Súdwest-Fryslân",
        },
        "datumAanvangAdreshouding": {
            "dag": 1,
            "jaar": 2011,
            "datum": "2011-01-01",
            "maand": 1,
        },
        "datumInschrijvingInGemeente": {
            "dag": 1,
            "jaar": 2011,
            "datum": "2011-01-01",
            "maand": 1,
        },
    },
    "burgerservicenummer": "999990901",
    "geslachtsaanduiding": "vrouw",
}

SMALL_RESPONSE = {
    "_links": {
        "self": {
            "href": (
                "https://acc.api.secure.amsterdam.nl"
                "/gob_stuf/brp/ingeschrevenpersonen/230164419"
            )
        }
    },
    "geslachtsaanduiding": "",
    "burgerservicenummer": "230164419",  # from acc, is faked data
    "verblijfplaats": {
        "functieAdres": "woonadres",
        "naamOpenbareRuimte": "Cycladenlaan",
        "huisnummer": "41",
        "postcode": "1060MB",
        "woonplaatsnaam": "Amsterdam",
        "straatnaam": "Cycladenlaan",
        "gemeenteVanInschrijving": {"code": "0363", "omschrijving": "Amsterdam"},
        "vanuitVertrokkenOnbekendWaarheen": False,
    },
}

SUCCESS_TESTS = {
    "default": (
        DEFAULT_RESPONSE,
        {
            "schema": "https://schemas.data.amsterdam.nl/datasets/remote/brp/dataset#ingeschrevenpersonen",  # noqa: E501
            "_links": {
                "self": {"href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"}
            },
            **DEFAULT_RESPONSE,
        },
    ),
    "small": (
        SMALL_RESPONSE,
        {
            "schema": "https://schemas.data.amsterdam.nl/datasets/remote/brp/dataset#ingeschrevenpersonen",  # noqa: E501
            "_links": {
                "self": {"href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"}
            },
            "verblijfplaats": {
                "postcode": "1060MB",
                "huisnummer": "41",
                "straatnaam": "Cycladenlaan",
                "functieAdres": "woonadres",
                "gemeenteVanInschrijving": {
                    "code": "0363",
                    "omschrijving": "Amsterdam",
                },
            },
            "burgerservicenummer": "230164419",
            "geslachtsaanduiding": "",
        },
    ),
}

CSV_HEADER = (
    "Schema,Geslachtsaanduiding,Leeftijd,Burgerservicenummer"
    ",Naam.Aanduidingnaamgebruik,Naam.Voornamen,Naam.Voorletters"
    ",Naam.Geslachtsnaam,Naam.Voorvoegsel"
    ",Geboorte.Datum.Datum,Geboorte.Datum.Jaar,Geboorte.Datum.Maand,Geboorte.Datum.Dag"
    ",Verblijfplaats.Functieadres,Verblijfplaats.Huisnummer,Verblijfplaats.Postcode"
    ",Verblijfplaats.Straatnaam"
    ",Verblijfplaats.Datumaanvangadreshouding.Datum"
    ",Verblijfplaats.Datumaanvangadreshouding.Jaar"
    ",Verblijfplaats.Datumaanvangadreshouding.Maand"
    ",Verblijfplaats.Datumaanvangadreshouding.Dag"
    ",Verblijfplaats.Datuminschrijvingingemeente.Datum"
    ",Verblijfplaats.Datuminschrijvingingemeente.Jaar"
    ",Verblijfplaats.Datuminschrijvingingemeente.Maand"
    ",Verblijfplaats.Datuminschrijvingingemeente.Dag"
    ",Verblijfplaats.Gemeentevaninschrijving.Code"
    ",Verblijfplaats.Gemeentevaninschrijving.Omschrijving\r\n"
)

as_is = lambda data: data


class FormatTestInput(NamedTuple):
    remote_response: dict
    format: str
    parser: callable
    expected_type: str
    expected_data: Union[str, dict]


SUCCESS_FORMAT_TESTS = {
    "csv-default": FormatTestInput(
        DEFAULT_RESPONSE,
        "csv",
        as_is,
        "text/csv; charset=utf-8",
        CSV_HEADER
        + "https://schemas.data.amsterdam.nl/datasets/remote/brp/dataset#ingeschrevenpersonen"
        + ",vrouw,77,999990901,eigen,Ria,R.,Amstel,van,1942-08-12,1942,8,12,woonadres,6,8603XM"
        + ",Anjelierstraat,2011-01-01,2011,1,1,2011-01-01,2011,1,1,1900,Súdwest-Fryslân\r\n",
    ),
    "csv-small": FormatTestInput(
        SMALL_RESPONSE,
        "csv",
        as_is,
        "text/csv; charset=utf-8",
        CSV_HEADER
        + "https://schemas.data.amsterdam.nl/datasets/remote/brp/dataset#ingeschrevenpersonen"
        + ",,,230164419,,,,,,,,,,woonadres,41,1060MB,Cycladenlaan,,,,,,,,,0363,Amsterdam\r\n",
    ),
    "geojson-default": FormatTestInput(
        DEFAULT_RESPONSE,
        "geojson",
        orjson.loads,
        "application/geo+json; charset=utf-8",
        {
            "type": "Feature",
            "crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::4326"}, "type": "name"},
            "properties": {
                "_links": {
                    "self": {
                        "href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"
                    }
                },
                "burgerservicenummer": "999990901",
                "geboorte": {
                    "datum": {"dag": 12, "datum": "1942-08-12", "jaar": 1942, "maand": 8}
                },
                "geslachtsaanduiding": "vrouw",
                "leeftijd": 77,
                "naam": {
                    "aanduidingNaamgebruik": "eigen",
                    "geslachtsnaam": "Amstel",
                    "voorletters": "R.",
                    "voornamen": "Ria",
                    "voorvoegsel": "van",
                },
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/remote/brp/dataset#ingeschrevenpersonen"
                ),
                "verblijfplaats": {
                    "datumAanvangAdreshouding": {
                        "dag": 1,
                        "datum": "2011-01-01",
                        "jaar": 2011,
                        "maand": 1,
                    },
                    "datumInschrijvingInGemeente": {
                        "dag": 1,
                        "datum": "2011-01-01",
                        "jaar": 2011,
                        "maand": 1,
                    },
                    "functieAdres": "woonadres",
                    "gemeenteVanInschrijving": {"code": "1900", "omschrijving": "Súdwest-Fryslân"},
                    "huisnummer": "6",
                    "postcode": "8603XM",
                    "straatnaam": "Anjelierstraat",
                },
            },
        },
    ),
    "geojson-small": FormatTestInput(
        SMALL_RESPONSE,
        "geojson",
        orjson.loads,
        "application/geo+json; charset=utf-8",
        {
            "type": "Feature",
            "crs": {"properties": {"name": "urn:ogc:def:crs:EPSG::4326"}, "type": "name"},
            "properties": {
                "_links": {
                    "self": {
                        "href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"
                    }
                },
                "burgerservicenummer": "230164419",
                "geslachtsaanduiding": "",
                "schema": (
                    "https://schemas.data.amsterdam.nl"
                    "/datasets/remote/brp/dataset#ingeschrevenpersonen"
                ),
                "verblijfplaats": {
                    "functieAdres": "woonadres",
                    "gemeenteVanInschrijving": {"code": "0363", "omschrijving": "Amsterdam"},
                    "huisnummer": "41",
                    "postcode": "1060MB",
                    "straatnaam": "Cycladenlaan",
                },
            },
        },
    ),
}


@pytest.fixture()
def urllib3_mocker() -> Responses:
    responses = Responses()
    with responses:
        yield responses


class AuthorizedResponse:
    """Callback for urllib3_mock that sends a fixed response
    only if the client sends an Authentication header.
    """

    def __init__(self, body: Any):
        self._body = orjson.dumps(body)

    def __call__(self, request):
        if "Authorization" in request.headers:
            return (HTTP_200_OK, {}, self._body)
        else:
            return (HTTP_403_FORBIDDEN, {}, "no Authorization received")


@pytest.mark.django_db
def test_remote_detail_view_with_profile_scope(
    api_client,
    fetch_auth_token,
    router,
    urllib3_mocker,
    brp_schema_json,
    brp_endpoint_url,
):
    models.Profile.create_for_schema(
        ProfileSchema.from_dict(
            {
                "name": "profiel",
                "scopes": ["PROFIEL/SCOPE"],
                "datasets": {
                    "brp_test": {
                        "tables": {
                            "ingeschrevenpersonen": {
                                "mandatoryFilterSets": [
                                    ["id"],
                                ],
                            }
                        }
                    }
                },
            }
        )
    )

    # creating custom brp2 copy, so a freshly created remote view
    # has a new copy of the patched schema object.
    brp_schema_json["id"] = "brp_test"
    brp_schema_json["auth"] = ["DATASET/SCOPE"]
    models.Dataset.objects.create(
        name="brp_test",
        schema_data=json.dumps(brp_schema_json),
        enable_db=False,
        endpoint_url=brp_endpoint_url.replace("brp", "brp_test"),
        auth=brp_schema_json["auth"],
    )
    router.reload()

    remote_response, local_response = SUCCESS_TESTS["default"]
    urllib3_mocker.add_callback(
        "GET",
        "/unittest/brp_test/ingeschrevenpersonen/999990901",
        callback=AuthorizedResponse(remote_response),
        content_type="application/json",
    )
    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp_test-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["DATASET/SCOPE", "PROFIEL/SCOPE"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200, response.data


@pytest.mark.django_db
@pytest.mark.parametrize("test_name", list(SUCCESS_TESTS.keys()))
def test_remote_detail_view(
    api_client, fetch_auth_token, brp_dataset, urllib3_mocker, test_name, filled_router
):
    """Prove that the remote router can proxy the other service."""
    remote_response, local_response = SUCCESS_TESTS[test_name]
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps(remote_response),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)
    assert response.status_code == 200, data
    assert data == local_response, data


@pytest.mark.django_db
@pytest.mark.parametrize("test_name", list(SUCCESS_FORMAT_TESTS.keys()))
def test_remote_detail_view_formats(
    api_client, fetch_auth_token, brp_dataset, urllib3_mocker, test_name, filled_router
):
    """Prove that the remote router can proxy the other service."""
    test_input: FormatTestInput = SUCCESS_FORMAT_TESTS[test_name]
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps(test_input.remote_response),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(
        url, data={"_format": test_input.format}, HTTP_AUTHORIZATION=f"Bearer {token}"
    )
    data = test_input.parser(read_response(response))
    assert response.status_code == 200, data
    assert response["content-type"] == test_input.expected_type
    assert data == test_input.expected_data


@pytest.mark.django_db
def test_remote_schema_validation(
    api_client, fetch_auth_token, router, brp_dataset, urllib3_mocker, filled_router
):
    """Prove that the schema is validated."""
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps({"secret": "I should not appear in the error response or the log"}),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)
    assert response["content-type"] == "application/problem+json"  # check before reading

    assert response.status_code == 502, data
    assert response["content-type"] == "application/problem+json"  # and after
    assert data == {
        "type": "urn:apiexception:validation_errors",
        "code": "validation_errors",
        "title": "Invalid remote data",
        "status": 502,
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/",
        "detail": "Some fields in the remote's response did not match the schema",
    }

    # Same, but now for a list view.
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen",
        body=orjson.dumps([{"secret": "I should not appear in the error response or the log"}]),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-list")
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)
    assert response["content-type"] == "application/problem+json"  # check before reading

    assert response.status_code == 502, data
    assert response["content-type"] == "application/problem+json"  # and after
    assert data == {
        "type": "urn:apiexception:validation_errors",
        "code": "validation_errors",
        "title": "Invalid remote data",
        "status": 502,
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/",
        "detail": "Some fields in the remote's response did not match the schema",
    }


@pytest.mark.django_db
def test_remote_400_problem_json(
    api_client, fetch_auth_token, router, brp_dataset, urllib3_mocker
):
    """Prove that the schema is validated."""
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901342",
        status=400,
        body=orjson.dumps(
            {
                "type": (
                    "https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html"
                    "#sec10.4.1 400 Bad Request"
                ),
                "title": "Een of meerdere parameters zijn niet correct.",
                "status": 400,
                "detail": "De foutieve parameter(s) zijn: burgerservicenummer.",
                "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901342/",
                "code": "paramsValidation",
                "invalid-params": [
                    {
                        "code": "maxLength",
                        "reason": "Waarde is langer dan maximale lengte 9.",
                        "name": "burgerservicenummer",
                    }
                ],
            }
        ),
        content_type="application/problem+json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901342"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)
    assert response["content-type"] == "application/problem+json"  # check before reading

    assert response.status_code == 400, data
    assert data == {
        "type": "urn:apiexception:parse_error",  # changed for consistency!
        "title": "Malformed request.",
        "status": 400,
        "detail": "De foutieve parameter(s) zijn: burgerservicenummer.",
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901342/",
        "code": "parse_error",  # changed for consistency!
        "invalid-params": [
            {
                "code": "maxLength",
                "reason": "Waarde is langer dan maximale lengte 9.",
                "name": "burgerservicenummer",
            }
        ],
    }


@pytest.mark.django_db
def test_remote_404_problem_json(
    api_client, fetch_auth_token, router, brp_dataset, urllib3_mocker
):
    """Prove that the schema is validated."""
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/119990901",
        status=404,
        body=orjson.dumps(
            {
                "type": (
                    "https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html"
                    "#sec10.4.5 404 Not Found"
                ),
                "title": "Opgevraagde resource bestaat niet.",
                "status": 404,
                "detail": "Ingeschreven persoon niet gevonden met burgerservicenummer 119990901.",
                "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/119990901/",
                "code": "notFound",
            }
        ),
        content_type="application/problem+json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "119990901"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response["content-type"] == "application/problem+json"  # check before reading
    data = read_response_json(response)

    assert response.status_code == 404, data
    assert response["content-type"] == "application/problem+json"  # and after
    assert data == {
        "type": "urn:apiexception:not_found",  # changed for consistency!
        "title": "Not found.",
        "status": 404,
        "detail": "Ingeschreven persoon niet gevonden met burgerservicenummer 119990901.",
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/119990901/",
        "code": "not_found",  # changed for consistency!
    }


@pytest.mark.django_db
@pytest.mark.parametrize("remote_status", [401, 403])
def test_brp_not_authenticated(
    api_client, fetch_auth_token, filled_router, brp_dataset, urllib3_mocker, remote_status
):
    """Test auth error handling: 401 and 403 should both become 403."""

    urllib3_mocker.add_callback(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        callback=lambda request: (remote_status, {}, "foo"),
        content_type="application/json",
    )

    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["BRP/R"])  # We need a token to get through the proxy.
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)

    assert response.status_code == 403, data
    assert data["detail"].startswith(str(remote_status))


@pytest.mark.django_db
def test_remote_timeout(api_client, fetch_auth_token, router, brp_dataset, urllib3_mocker):
    """Prove that the remote router can proxy the other service."""

    def _raise_timeout(request):
        raise urllib3.exceptions.TimeoutError()

    router.reload()
    urllib3_mocker.add_callback(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        callback=_raise_timeout,
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["BRP/R"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)

    assert response.status_code == 504, data
    assert data == {
        "type": "urn:apiexception:gateway_timeout",
        "title": "Connection failed (server timeout)",
        "detail": "Connection failed (server timeout)",
        "status": 504,
    }


# Load Haal Centraal BRK example data (from
# https://vng-realisatie.github.io/Haal-Centraal-BRK-bevragen/getting-started)
# and desired outputs.
HCBRK_FILES = Path(__file__).parent.parent.parent / "files" / "haalcentraalbrk"
HCBRK_NATUURLIJKPERSOON = (HCBRK_FILES / "hcbrk_natuurlijkpersoon.json").read_text()
HCBRK_ONROERENDE_ZAAK = (HCBRK_FILES / "hcbrk_onroerendezaak.json").read_text()
DSO_NATUURLIJKPERSOON = json.load(open(HCBRK_FILES / "dso_natuurlijkpersoon.json"))
DSO_NATUURLIJKPERSOON_UNAUTH = json.load(open(HCBRK_FILES / "dso_natuurlijkpersoon_unauth.json"))
DSO_ONROERENDE_ZAAK = json.load(open(HCBRK_FILES / "dso_onroerendezaak.json"))

DSO_ONROERENDE_ZAAK_UNAUTH = {
    field: value
    for field, value in DSO_ONROERENDE_ZAAK.items()
    if field
    not in (
        "koopsom",
        "aardCultuurBebouwd",
        "toelichtingBewaarder",
        "hypotheekIdentificaties",
        "zakelijkGerechtigdeIdentificaties",
        "privaatrechtelijkeBeperkingIdentificaties",
    )
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "case",
    [
        {
            # Natuurlijke persoon, with full authorisation.
            "table": "kadasternatuurlijkpersonen",
            "ident": 70882239,
            "scopes": ["BRK/RS", "BRK/RSN", "TEST/VOORNAAMPARTNER"],
            "from_kadaster": HCBRK_NATUURLIJKPERSOON,
            "output": DSO_NATUURLIJKPERSOON,
        },
        {
            # Natuurlijke persoon, with minimal authorisation.
            "table": "kadasternatuurlijkpersonen",
            "ident": 70882239,
            "scopes": ["BRK/RS"],
            "from_kadaster": HCBRK_NATUURLIJKPERSOON,
            "output": DSO_NATUURLIJKPERSOON_UNAUTH,
        },
        {
            # Onroerende zaak, with full authorisation.
            "table": "kadastraalonroerendezaken",
            "ident": 76870487970000,
            "scopes": ["BRK/RS", "BRK/RO"],
            "from_kadaster": HCBRK_ONROERENDE_ZAAK,
            "output": DSO_ONROERENDE_ZAAK,
        },
        {
            # Onroerende zaak, with minimal authorisation.
            "table": "kadastraalonroerendezaken",
            "ident": 76870487970000,
            "scopes": ["BRK/RS"],
            "from_kadaster": HCBRK_ONROERENDE_ZAAK,
            "output": DSO_ONROERENDE_ZAAK_UNAUTH,
        },
    ],
)
def test_haalcentraalbrk_client(
    api_client, fetch_auth_token, router, hcbrk_dataset, urllib3_mocker, case
):
    """Test Haal Centraal BRK remote client."""

    def respond(request):
        assert "Authorization" not in request.headers
        assert "X-Api-Key" in request.headers
        assert request.body is None
        return (200, {"Content-Crs": "epsg:28992"}, case["from_kadaster"])

    table, ident = case["table"], case["ident"]

    router.reload()
    urllib3_mocker.add_callback(
        "GET",
        f"/esd/bevragen/v1/{table}/{ident}",
        callback=respond,
        content_type="application/json",
    )

    url = reverse(f"dynamic_api:haalcentraalbrk-{table}-detail", kwargs={"pk": str(ident)})
    token = fetch_auth_token(case["scopes"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)

    assert response.status_code == 200, data
    assert data == case["output"]


@pytest.mark.django_db
def test_haalcentraalbrk_geojson(
    api_client, fetch_auth_token, router, hcbrk_dataset, urllib3_mocker
):
    """Test whether remote API responses are properly converted."""

    def respond(request):
        assert "Authorization" not in request.headers
        assert "X-Api-Key" in request.headers
        assert request.body is None
        return (200, {"Content-Crs": "epsg:28992"}, HCBRK_ONROERENDE_ZAAK)

    router.reload()
    urllib3_mocker.add_callback(
        "GET",
        "/esd/bevragen/v1/kadastraalonroerendezaken/76870487970000",
        callback=respond,
        content_type="application/json",
    )

    url = reverse(
        "dynamic_api:haalcentraalbrk-kadastraalonroerendezaken-detail",
        kwargs={"pk": "76870487970000"},
    )
    token = fetch_auth_token(["BRK/RS", "BRK/RO"])
    response = api_client.get(url, {"_format": "geojson"}, HTTP_AUTHORIZATION=f"Bearer {token}")
    data = read_response_json(response)

    assert response.status_code == 200, data
    rounder = lambda p: [round(c, 6) for c in p]

    # Prove that coordinates are properly transformed from RD/NEW to WGS84
    plaatscoordinaten = data["properties"]["plaatscoordinaten"]
    assert plaatscoordinaten["type"] == "Point"
    assert rounder(plaatscoordinaten["coordinates"]) == [5.966022, 52.164126]


REMOTE_SCHEMA = DatasetTableSchema.from_dict(
    {
        "id": "mytable",
        "schemaType": "table",
        "schema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    }
)


@pytest.mark.parametrize(
    "case",
    [
        ("http://remote", "http://remote/foo?bar=baz"),
        ("http://remote/", "http://remote/foo?bar=baz"),
        ("http://remote/quux/{table_id}", "http://remote/quux/mytable/foo?bar=baz"),
        ("http://remote/quux/{table_id}/", "http://remote/quux/mytable/foo?bar=baz"),
    ],
)
def test_make_url(case):
    base, expect = case
    client = RemoteClient(base, REMOTE_SCHEMA)
    assert client._make_url("foo", {"bar": "baz"}) == expect
