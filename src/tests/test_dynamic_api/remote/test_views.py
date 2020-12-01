import orjson
import pytest
import urllib3
from urllib3_mock import Responses
from django.urls import reverse
from schematools.contrib.django import models

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
            "schema": "https://schemas.data.amsterdam.nl/datasets/brp/brp#ingeschrevenpersonen",
            "_links": {
                "self": {
                    "href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"
                }
            },
            **DEFAULT_RESPONSE,
        },
    ),
    "small": (
        SMALL_RESPONSE,
        {
            "schema": "https://schemas.data.amsterdam.nl/datasets/brp/brp#ingeschrevenpersonen",
            "_links": {
                "self": {
                    "href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"
                }
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


@pytest.fixture()
def urllib3_mocker() -> Responses:
    responses = Responses()
    with responses:
        yield responses


@pytest.mark.django_db
@pytest.mark.parametrize("test_name", list(SUCCESS_TESTS.keys()))
def test_remote_detail_view_with_profile_scope(
    api_client, fetch_auth_token, router, brp_dataset, urllib3_mocker, test_name
):
    models.Profile.objects.create(
        name="profiel",
        scopes=["PROFIEL/SCOPE"],
        schema_data={
            "datasets": {
                "brp": {
                    "tables": {
                        "ingeschrevenpersonen": {
                            "mandatoryFilterSets": [
                                ["id"],
                            ],
                        }
                    }
                }
            }
        },
    )
    remote_response, local_response = SUCCESS_TESTS[test_name]
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps(remote_response),
        content_type="application/json",
    )
    # Prove that URLs can now be resolved.
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"}
    )
    models.Dataset.objects.filter(name="brp").update(auth="DATASET/SCOPE")
    token = fetch_auth_token(["PROFIEL/SCOPE"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200, response.data
    assert response.json() == local_response, response.data


@pytest.mark.django_db
@pytest.mark.parametrize("test_name", list(SUCCESS_TESTS.keys()))
def test_remote_detail_view(api_client, router, brp_dataset, urllib3_mocker, test_name):
    """Prove that the remote router can proxy the other service."""
    remote_response, local_response = SUCCESS_TESTS[test_name]
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps(remote_response),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"}
    )
    response = api_client.get(url)

    # To test: print(json.dumps(response.json(), indent=2))
    assert response.status_code == 200, response.data
    assert response.json() == local_response, response.data


@pytest.mark.django_db
def test_remote_schema_validation(api_client, router, brp_dataset, urllib3_mocker):
    """Prove that the schema is validated."""
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps({"foo": "bar"}),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"}
    )
    response = api_client.get(url)

    assert response.status_code == 502, response.data
    assert response["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "urn:apiexception:validation_errors",
        "code": "validation_errors",
        "title": "Invalid remote data",
        "status": 502,
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/",
        "detail": "These schema fields did not validate:",
        "x-validation-errors": {"burgerservicenummer": ["This field is required."]},
        "x-raw-response": {"foo": "bar"},
    }, response.data


@pytest.mark.django_db
def test_remote_400_problem_json(api_client, router, brp_dataset, urllib3_mocker):
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
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901342"}
    )
    response = api_client.get(url)

    assert response.status_code == 400, response.data
    assert response["content-type"] == "application/problem+json"
    assert response.json() == {
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
    }, response.data


@pytest.mark.django_db
def test_remote_404_problem_json(api_client, router, brp_dataset, urllib3_mocker):
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
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "119990901"}
    )
    response = api_client.get(url)

    assert response.status_code == 404, response.data
    assert response["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "urn:apiexception:not_found",  # changed for consistency!
        "title": "Not found.",
        "status": 404,
        "detail": "Ingeschreven persoon niet gevonden met burgerservicenummer 119990901.",
        "instance": "http://testserver/v1/remote/brp/ingeschrevenpersonen/119990901/",
        "code": "not_found",  # changed for consistency!
    }, response.data


@pytest.mark.django_db
def test_remote_timeout(api_client, router, brp_dataset, urllib3_mocker):
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
    url = reverse(
        "dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"}
    )
    response = api_client.get(url)

    assert response.status_code == 504, response.data
    assert response.json() == {
        "type": "urn:apiexception:gateway_timeout",
        "title": "Connection failed (server timeout)",
        "detail": "Connection failed (server timeout)",
        "status": 504,
    }, response.data
