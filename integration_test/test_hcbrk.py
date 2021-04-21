# End-to-end test against HCBRK (Kadaster).

import os
import time
from typing import List

import orjson
import pytest
import requests
from jwcrypto.jwk import JWK
from jwcrypto.jwt import JWT
from more_ds.network.url import URL

API = os.getenv("DSO_API")


# Copied from src/settings.py.
JWKS_TEST_KEY = JWK(
    kty="EC",
    key_ops=["verify", "sign"],
    kid="2aedafba-8170-4064-b704-ce92b7c89cc6",
    crv="P-256",
    x="6r8PYwqfZbq_QzoMA4tzJJsYUIIXdeyPA27qTgEJCDw=",
    y="Cf2clfAfFuuCB06NMfIat9ultkMyrMQO9Hd2H7O9ZVE=",
    d="N1vu0UQUp0vLfaNeM0EDbl4quvvL6m_ltjoAXXzkI3U=",
)


# From test server.

NATUURLIJK_PERSOON_DSO = {
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
    "_links": {"self": {"href": URL(API) / "/v1/hcbrk/kadasternatuurlijkpersonen/70882239/"}},
}


ONROERENDE_ZAAK_DSO = {
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
    "_links": {"self": {"href": URL(API) / "/v1/hcbrk/kadastraalonroerendezaken/76870487970000/"}},
}


def auth_token(*scopes: List[str]) -> str:
    """Returns a serialized JWT using the test key."""
    now = int(time.time())
    valid = 1800

    claims = {
        "iat": now,
        "exp": now + valid,
        "scopes": scopes,
        "sub": "tester@example.com",
    }

    kid = JWKS_TEST_KEY.key_id
    token = JWT(header={"alg": "ES256", "kid": kid}, claims=claims)
    token.make_signed_token(JWKS_TEST_KEY)
    return token.serialize()


def test_hcbrk_natuurlijkepersonen():
    if not API:
        pytest.skip("Set DSO_API to the base url")

    url = URL(API) / "/v1/hcbrk/kadasternatuurlijkpersonen/70882239/"
    resp = requests.get(url, headers={"Authorization": "Bearer " + auth_token("BRK/RSN")})

    assert resp.status_code == 200

    content = orjson.loads(resp.content)
    assert content == NATUURLIJK_PERSOON_DSO


def test_hcbrk_onroerendezaken():
    if not API:
        pytest.skip("Set DSO_API to the base url")

    url = URL(API) / "/v1/hcbrk/kadastraalonroerendezaken/76870487970000/"
    resp = requests.get(url, headers={"Authorization": "Bearer " + auth_token("BRK/RSN")})

    assert resp.status_code == 200

    content = orjson.loads(resp.content)
    assert content == ONROERENDE_ZAAK_DSO
