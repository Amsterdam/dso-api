import orjson
import pytest
import urllib3
from django.urls import reverse
from schematools.contrib.django import models
from schematools.types import DatasetTableSchema
from urllib3_mock import Responses

from dso_api.dynamic_api.remote.clients import RemoteClient
from tests.utils import read_response_json

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
                "self": {"href": "http://testserver/v1/remote/brp/ingeschrevenpersonen/999990901/"}
            },
            **DEFAULT_RESPONSE,
        },
    ),
    "small": (
        SMALL_RESPONSE,
        {
            "schema": "https://schemas.data.amsterdam.nl/datasets/brp/brp#ingeschrevenpersonen",
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


@pytest.fixture()
def urllib3_mocker() -> Responses:
    responses = Responses()
    with responses:
        yield responses


@pytest.mark.django_db
def test_remote_detail_view_with_profile_scope(
    api_client,
    fetch_auth_token,
    router,
    urllib3_mocker,
    brp_schema_json,
    brp_endpoint_url,
):
    models.Profile.objects.create(
        name="profiel",
        scopes=["PROFIEL/SCOPE"],
        schema_data={
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
            }
        },
    )
    # creating custom brp2 copy, as ttl_cache will keep auth value after this test
    # which breaks the other tests
    brp_schema_json["id"] = "brp_test"
    models.Dataset.objects.create(
        name="brp_test",
        schema_data=brp_schema_json,
        enable_db=False,
        endpoint_url=brp_endpoint_url.replace("brp", "brp_test"),
        auth=["DATASET/SCOPE"],
    )
    remote_response, local_response = SUCCESS_TESTS["default"]
    router.reload()
    urllib3_mocker.add(
        "GET",
        "/unittest/brp_test/ingeschrevenpersonen/999990901",
        body=orjson.dumps(remote_response),
        content_type="application/json",
    )
    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp_test-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    token = fetch_auth_token(["PROFIEL/SCOPE"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200, response.data


@pytest.mark.django_db
@pytest.mark.parametrize("test_name", list(SUCCESS_TESTS.keys()))
def test_remote_detail_view(api_client, brp_dataset, urllib3_mocker, test_name, filled_router):
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
    response = api_client.get(url)
    data = read_response_json(response)
    assert response.status_code == 200, data
    assert data == local_response, data


@pytest.mark.django_db
def test_remote_schema_validation(api_client, router, brp_dataset, urllib3_mocker, filled_router):
    """Prove that the schema is validated."""
    urllib3_mocker.add(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        body=orjson.dumps({"foo": "bar"}),
        content_type="application/json",
    )

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    response = api_client.get(url)
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
        "detail": "These schema fields did not validate:",
        "x-validation-errors": {"burgerservicenummer": ["This field is required."]},
        "x-raw-response": {"foo": "bar"},
    }


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
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901342"})
    response = api_client.get(url)
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
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "119990901"})
    response = api_client.get(url)
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
    api_client, filled_router, brp_dataset, urllib3_mocker, remote_status
):
    """Test auth error handling: 401 and 403 should both become 403."""

    urllib3_mocker.add_callback(
        "GET",
        "/unittest/brp/ingeschrevenpersonen/999990901",
        callback=lambda request: (remote_status, {}, None),
        content_type="application/json",
    )

    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    response = api_client.get(url)
    assert response.status_code == 403


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
    url = reverse("dynamic_api:brp-ingeschrevenpersonen-detail", kwargs={"pk": "999990901"})
    response = api_client.get(url)
    data = read_response_json(response)

    assert response.status_code == 504, data
    assert data == {
        "type": "urn:apiexception:gateway_timeout",
        "title": "Connection failed (server timeout)",
        "detail": "Connection failed (server timeout)",
        "status": 504,
    }


# https://vng-realisatie.github.io/Haal-Centraal-BRK-bevragen/getting-started
HCBRK_NATUURLIJKPERSOON = (
    '{"identificatie":"70882239","omschrijving":"Willem Jansens","dom'
    'ein":"NL.IMKAD.Persoon","beschikkingsbevoegdheid":{"code":"6","w'
    'aarde":"Voogdij"},"woonadres":{"straat":"Burggang","huisnummer":'
    '1,"huisletter":"D","huisnummertoevoeging":"9","postcode":"4331AD'
    '","woonplaats":"MIDDELBURG","adresregel1":"Burggang 1D-9","adres'
    'regel2":"4331AD MIDDELBURG"},"postadres":{"straat":"Abdij","huis'
    'nummer":2,"huisletter":"E","huisnummertoevoeging":"8","postcode"'
    ':"4331BK","woonplaats":"MIDDELBURG","adresregel1":"Abdij 2E-8","'
    'adresregel2":"4331BK MIDDELBURG"},"kadastraalOnroerendeZaakIdent'
    'ificaties":["76870487970000","76870482670000"],"geslachtsaanduid'
    'ing":"man","heeftPartnerschap":[{"naam":{"geslachtsnaam":"Jansen'
    's","voornamen":"Sidonia"}}],"naam":{"geslachtsnaam":"Jansens","v'
    'oornamen":"Willem","aanschrijfwijze":"W. Jansens","aanhef":"Geac'
    'hte heer Jansens","gebruikInLopendeTekst":"de heer Jansens"},"ge'
    'boorte":{"plaats":"OSS","datum":{"dag":1,"datum":"1971-11-01","j'
    'aar":1971,"maand":11},"land":{"code":"6030","waarde":"Nederland"'
    '}},"_links":{"self":{"href":"/kadasternatuurlijkpersonen/7088223'
    '9"},"kadastraalOnroerendeZaken":[{"href":"/kadastraalonroerendez'
    'aken/{kadastraalOnroerendeZaakIdentificaties}","templated":true}'
    '],"zakelijkGerechtigden":[{"href":"/kadastraalonroerendezaken/76'
    '870487970000/zakelijkgerechtigden/30493367"},{"href":"/kadastraa'
    'lonroerendezaken/76870482670000/zakelijkgerechtigden/1000003519"'
    "}]}}"
)


DSO_NATUURLIJK_PERSOON = {
    "schema": "https://schemas.data.amsterdam.nl/datasets/hcbrk/hcbrk#kadasternatuurlijkpersonen",
    "naam": {
        "aanhef": "Geachte heer Jansens",
        "voornamen": "Willem",
        "geslachtsnaam": "Jansens",
        "aanschrijfwijze": "W. Jansens",
        "gebruikInLopendeTekst": "de heer Jansens",
    },
    "domein": "NL.IMKAD.Persoon",
    "geboorte": {"datum": {"dag": 1, "jaar": 1971, "datum": "1971-11-01", "maand": 11}},
    "woonadres": {"adresregel1": "Burggang 1D-9", "adresregel2": "4331AD MIDDELBURG"},
    "omschrijving": "Willem Jansens",
    "identificatie": "70882239",
    "heeftPartnerschap": [{"naam": {"voornamen": "Sidonia", "geslachtsnaam": "Jansens"}}],
    "geslachtsaanduiding": "man",
    "kadastraalOnroerendeZaakIdentificaties": ["76870487970000", "76870482670000"],
    "_links": {
        "self": {"href": "http://testserver/v1/remote/hcbrk/kadasternatuurlijkpersonen/70882239/"}
    },
}


HCBRK_ONROERENDE_ZAAK = (
    '{"identificatie":"76870487970000","domein":"NL.IMKAD.KadastraalO'
    'bject","begrenzingPerceel":{"type":"Polygon","coordinates":[[[19'
    "4598.014,464150.355],[194607.893,464150.728],[194605.599,464174."
    "244],[194603.893,464174.212],[194601.799,464174.231],[194599.706"
    ",464174.307],[194598.925,464174.341],[194598.143,464174.324],[19"
    "4597.363,464174.257],[194596.59,464174.14],[194597.354,464166.63"
    '3],[194598.014,464150.355]]]},"perceelnummerRotatie":-86.1,"plaa'
    'tscoordinaten":{"type":"Point","coordinates":[194602.722,464154.'
    '308]},"koopsom":{"koopsom":185000,"koopjaar":2015},"toelichtingB'
    'ewaarder":"Hier kan een toelichting staan van de bewaarder.","ty'
    'pe":"perceel","aardCultuurBebouwd":{"code":"11","waarde":"Wonen"'
    '},"kadastraleAanduiding":"Beekbergen K 4879","kadastraleGrootte"'
    ':{"soortGrootte":{"code":"1","waarde":"Vastgesteld"},"waarde":22'
    '4},"perceelnummerVerschuiving":{"deltax":-6.453,"deltay":2.075},'
    '"adressen":[{"straat":"Atalanta","huisnummer":29,"postcode":"736'
    '1EW","woonplaats":"Beekbergen","nummeraanduidingIdentificatie":"'
    '0200200000003734","adresregel1":"Atalanta 29","adresregel2":"736'
    '1EW Beekbergen","koppelingswijze":{"code":"ADM_GEO","waarde":"ad'
    'ministratief en geometrisch"},"adresseerbaarObjectIdentificatie"'
    ':"0200010000017317"}],"zakelijkGerechtigdeIdentificaties":["3049'
    '3367","30493368"],"privaatrechtelijkeBeperkingIdentificaties":["'
    '30336965"],"hypotheekIdentificaties":["35052041"],"isVermeldInSt'
    'ukdeelIdentificaties":["1029999990"],"stukIdentificaties":["2017'
    '0102999999"],"_links":{"self":{"href":"/kadastraalonroerendezake'
    'n/76870487970000"},"zakelijkGerechtigden":[{"href":"/kadastraalo'
    "nroerendezaken/76870487970000/zakelijkgerechtigden/{zakelijkGere"
    'chtigdeIdentificaties}","templated":true}],"privaatrechtelijkeBe'
    'perkingen":[{"href":"/kadastraalonroerendezaken/76870487970000/p'
    "rivaatrechtelijkebeperkingen/{privaatrechtelijkeBeperkingIdentif"
    'icaties}","templated":true}],"hypotheken":[{"href":"/kadastraalo'
    "nroerendezaken/76870487970000/hypotheken/{hypotheekIdentificatie"
    's}","templated":true}],"stukken":[{"href":"/stukken/{stukIdentif'
    'icaties}","templated":true}],"stukdelen":[{"href":"/stukdelen/{i'
    'sVermeldInStukdeelIdentificaties}","templated":true}],"adressen"'
    ':[{"href":"https://api.bag.kadaster.nl/esd/huidigebevragingen/v1'
    '/adressen/{adressen.nummeraanduidingIdentificatie}","templated":'
    'true}],"adresseerbareObjecten":[{"href":"https://api.bag.kadaste'
    "r.nl/esd/huidigebevragingen/v1/adressen/adresseerbareobjecten/{a"
    'dressen.adresseerbaarObjectIdentificatie}","templated":true}]}}'
)


DSO_ONROERENDE_ZAAK = {
    "schema": "https://schemas.data.amsterdam.nl/datasets/hcbrk/hcbrk#kadastraalonroerendezaken",
    "type": "perceel",
    "domein": "NL.IMKAD.KadastraalObject",
    "koopsom": {"koopsom": 185000, "koopjaar": 2015},
    "adressen": [
        {
            "straat": "Atalanta",
            "postcode": "7361EW",
            "huisnummer": 29,
            "woonplaats": "Beekbergen",
            "adresregel1": "Atalanta 29",
            "adresregel2": "7361EW Beekbergen",
            "koppelingswijze": {"code": "ADM_GEO", "waarde": "administratief en geometrisch"},
            "nummeraanduidingIdentificatie": "0200200000003734",
        }
    ],
    "identificatie": "76870487970000",
    "begrenzingPerceel": {
        "type": "Polygon",
        "coordinates": [
            [
                [194598.014, 464150.355],
                [194607.893, 464150.728],
                [194605.599, 464174.244],
                [194603.893, 464174.212],
                [194601.799, 464174.231],
                [194599.706, 464174.307],
                [194598.925, 464174.341],
                [194598.143, 464174.324],
                [194597.363, 464174.257],
                [194596.59, 464174.14],
                [194597.354, 464166.633],
                [194598.014, 464150.355],
            ]
        ],
    },
    "kadastraleGrootte": {"waarde": "224", "soortGrootte": {"code": 1, "waarde": "Vastgesteld"}},
    "plaatscoordinaten": {"type": "Point", "coordinates": [194602.722, 464154.308]},
    "aardCultuurBebouwd": {"code": 11, "waarde": "Wonen"},
    "kadastraleAanduiding": "Beekbergen K 4879",
    "perceelnummerRotatie": -86.1,
    "toelichtingBewaarder": "Hier kan een toelichting staan van de bewaarder.",
    "hypotheekIdentificaties": ["35052041"],
    "perceelnummerVerschuiving": {"deltax": -6.453, "deltay": 2.075},
    "zakelijkGerechtigdeIdentificaties": ["30493367", "30493368"],
    "privaatrechtelijkeBeperkingIdentificaties": ["30336965"],
    "_links": {
        "self": {
            "href": "http://testserver/v1/remote/hcbrk/kadastraalonroerendezaken/76870487970000/"
        }
    },
}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "case",
    [
        ("kadasternatuurlijkpersonen", 70882239, HCBRK_NATUURLIJKPERSOON, DSO_NATUURLIJK_PERSOON),
        ("kadastraalonroerendezaken", 76870487970000, HCBRK_ONROERENDE_ZAAK, DSO_ONROERENDE_ZAAK),
    ],
)
def test_hcbrk_client(api_client, router, hcbrk_dataset, urllib3_mocker, case):
    """Test HCBRK remote client."""

    table, ident, from_hcbrk, output = case

    def get_natuurlijkpersoon(request):
        assert "Authorization" not in request.headers
        assert "X-Api-Key" in request.headers
        assert request.body is None
        return (200, set(), from_hcbrk)

    router.reload()
    urllib3_mocker.add_callback(
        "GET",
        f"/esd/bevragen/v1/{table}/{ident}",
        callback=get_natuurlijkpersoon,
        content_type="application/json",
    )

    url = reverse(f"dynamic_api:hcbrk-{table}-detail", kwargs={"pk": str(ident)})
    response = api_client.get(url)
    data = read_response_json(response)

    assert response.status_code == 200, data
    assert data == output


REMOTE_SCHEMA = DatasetTableSchema.from_dict(
    {
        "id": "mytable",
        "type": "table",
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
