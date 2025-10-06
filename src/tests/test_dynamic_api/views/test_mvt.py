from datetime import date, datetime

import mapbox_vector_tile
import pytest
from django.contrib.gis.geos import Point
from django.http.response import HttpResponse, HttpResponseBase, StreamingHttpResponse
from django.utils.timezone import get_current_timezone

from dso_api.dynamic_api.filters.values import AMSTERDAM_BOUNDS, DAM_SQUARE

CONTENT_TYPE = "application/vnd.mapbox-vector-tile"


@pytest.mark.django_db
class TestDatasetMVTIndexView:
    def test_mvt_index(
        self,
        api_client,
        afval_dataset,
        fietspaaltjes_dataset,
        filled_router,
        drf_request,
    ):
        """Prove that the MVT index view works."""
        response = api_client.get("/v1/mvt")
        assert response.status_code == 200

        # Prove that response contains the correct data
        BASE = drf_request.build_absolute_uri("/").rstrip("/")
        assert response.data == {
            "datasets": {
                "afvalwegingen": {
                    "id": "afvalwegingen",
                    "short_name": "afvalwegingen",
                    "service_name": "Afvalwegingen",
                    "status": "beschikbaar",
                    "description": "unit testing version of afvalwegingen",
                    "tags": [],
                    "terms_of_use": {
                        "government_only": False,
                        "pay_per_use": False,
                        "license": "CC0 1.0",
                    },
                    "versions": [
                        {
                            "api_url": f"{BASE}/v1/afvalwegingen",
                            "doc_url": f"{BASE}/v1/docs/generic/gis.html",
                            "header": "Standaardversie (v1)",
                            "mvt_url": f"{BASE}/v1/mvt/afvalwegingen",
                            "wfs_url": f"{BASE}/v1/wfs/afvalwegingen",
                        },
                        {
                            "api_url": f"{BASE}/v1/afvalwegingen/v1",
                            "doc_url": f"{BASE}/v1/docs/generic/gis.html",
                            "header": "Versie v1",
                            "mvt_url": f"{BASE}/v1/mvt/afvalwegingen/v1",
                            "wfs_url": f"{BASE}/v1/wfs/afvalwegingen/v1",
                        },
                    ],
                    "api_authentication": ["OPENBAAR"],
                    "api_type": "MVT",
                    "organization_name": "Gemeente Amsterdam",
                    "organization_oin": "00000001002564440000",
                    "contact": {
                        "email": "datapunt@amsterdam.nl",
                        "url": "https://github.com/Amsterdam/dso-api/issues",
                    },
                },
                "fietspaaltjes": {
                    "id": "fietspaaltjes",
                    "short_name": "fietspaaltjes",
                    "service_name": "fietspaaltjes",
                    "status": "beschikbaar",
                    "description": "",
                    "tags": [],
                    "terms_of_use": {
                        "government_only": False,
                        "pay_per_use": False,
                        "license": None,
                    },
                    "versions": [
                        {
                            "api_url": f"{BASE}/v1/fietspaaltjes",
                            "doc_url": f"{BASE}/v1/docs/generic/gis.html",
                            "header": "Standaardversie (v1)",
                            "mvt_url": f"{BASE}/v1/mvt/fietspaaltjes",
                            "wfs_url": f"{BASE}/v1/wfs/fietspaaltjes",
                        },
                        {
                            "api_url": f"{BASE}/v1/fietspaaltjes/v1",
                            "doc_url": f"{BASE}/v1/docs/generic/gis.html",
                            "header": "Versie v1",
                            "mvt_url": f"{BASE}/v1/mvt/fietspaaltjes/v1",
                            "wfs_url": f"{BASE}/v1/wfs/fietspaaltjes/v1",
                        },
                    ],
                    "api_authentication": ["OPENBAAR"],
                    "api_type": "MVT",
                    "organization_name": "Gemeente Amsterdam",
                    "organization_oin": "00000001002564440000",
                    "contact": {
                        "email": "datapunt@amsterdam.nl",
                        "url": "https://github.com/Amsterdam/dso-api/issues",
                    },
                },
            }
        }

    def test_mvt_index_disabled(
        self, api_client, disabled_afval_dataset, fietspaaltjes_dataset, filled_router
    ):
        """Prove that disabled API's are not listed."""
        response = api_client.get("/v1/mvt")
        assert response.status_code == 200
        assert set(response.data["datasets"].keys()) == {"fietspaaltjes"}


@pytest.mark.django_db
def test_mvt_single(api_client, afval_container, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/afvalwegingen/")
    assert response.status_code == 200
    assert b"/v1/mvt/afvalwegingen/containers/{z}/{x}/{y}.pbf" in response.content


@pytest.mark.django_db
def test_mvt_single_v1(api_client, afval_container, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/afvalwegingen/v1")
    assert response.status_code == 200
    assert b"/v1/mvt/afvalwegingen/v1/containers/{z}/{x}/{y}.pbf" in response.content


@pytest.mark.django_db
def test_mvt_tilejson(api_client, afval_container, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/afvalwegingen/tilejson.json")
    assert response.status_code == 200

    tilejson = response.json()
    assert tilejson == {
        "attribution": '(c) Gemeente <a href="https://amsterdam.nl">Amsterdam</a>',
        "bounds": AMSTERDAM_BOUNDS,
        "center": DAM_SQUARE,
        "description": "unit testing version of afvalwegingen",
        "fillzoom": None,
        "legend": None,
        "maxzoom": 15,
        "minzoom": 7,
        "name": "Afvalwegingen",
        "scheme": "xyz",
        "tilejson": "3.0.0",
        "tiles": [
            "http://testserver/v1/mvt/afvalwegingen/adres_loopafstand/{z}/{x}/{y}.pbf",
            "http://testserver/v1/mvt/afvalwegingen/containers/{z}/{x}/{y}.pbf",
        ],
        "vector_layers": [
            {
                "description": None,
                "fields": {
                    "geometry": "Geometrie",
                    "id": "row identifier",
                    "serienummer": "some serienumber",
                },
                "id": "adres_loopafstand",
                "maxzoom": 15,
                "minzoom": 7,
            },
            {
                "description": None,
                "fields": {
                    "clusterId": "Cluster-ID",
                    "datumCreatie": "Datum aangemaakt",
                    "datumLeegmaken": "Datum leeggemaakt",
                    "eigenaarNaam": "Naam van eigenaar",
                    "geometry": "Geometrie",
                    "id": "Container-ID",
                    "serienummer": "Serienummer van container",
                },
                "id": "containers",
                "maxzoom": 15,
                "minzoom": 7,
            },
        ],
        "version": "1.0.0",
    }


@pytest.mark.django_db
def test_mvt_tilejson_v1(api_client, afval_container, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/afvalwegingen/v1/tilejson.json")
    assert response.status_code == 200

    tilejson = response.json()
    assert tilejson == {
        "attribution": '(c) Gemeente <a href="https://amsterdam.nl">Amsterdam</a>',
        "bounds": AMSTERDAM_BOUNDS,
        "center": DAM_SQUARE,
        "description": "unit testing version of afvalwegingen",
        "fillzoom": None,
        "legend": None,
        "maxzoom": 15,
        "minzoom": 7,
        "name": "Afvalwegingen",
        "scheme": "xyz",
        "tilejson": "3.0.0",
        "tiles": [
            "http://testserver/v1/mvt/afvalwegingen/v1/adres_loopafstand/{z}/{x}/{y}.pbf",
            "http://testserver/v1/mvt/afvalwegingen/v1/containers/{z}/{x}/{y}.pbf",
        ],
        "vector_layers": [
            {
                "description": None,
                "fields": {
                    "geometry": "Geometrie",
                    "id": "row identifier",
                    "serienummer": "some serienumber",
                },
                "id": "adres_loopafstand",
                "maxzoom": 15,
                "minzoom": 7,
            },
            {
                "description": None,
                "fields": {
                    "clusterId": "Cluster-ID",
                    "datumCreatie": "Datum aangemaakt",
                    "datumLeegmaken": "Datum leeggemaakt",
                    "eigenaarNaam": "Naam van eigenaar",
                    "geometry": "Geometrie",
                    "id": "Container-ID",
                    "serienummer": "Serienummer van container",
                },
                "id": "containers",
                "maxzoom": 15,
                "minzoom": 7,
            },
        ],
        "version": "1.0.0",
    }


@pytest.mark.django_db
def test_mvt_tilejson_without_geo_fields_404s(api_client, aardgasverbruik_dataset, filled_router):
    """Prove that the MVT single view works."""
    response = api_client.get("/v1/mvt/aardgasverbruik/tilejson.json")
    assert response.status_code == 404


@pytest.mark.django_db
def test_mvt_content(
    api_client, afval_dataset, filled_router, afval_container_model, afval_cluster
):
    """Prove that the MVT view produces vector tiles."""

    # Coordinates below have been calculated using https://oms.wff.ch/calc.htm
    # and https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/.
    afval_container_model.objects.create(
        id=1,
        serienummer="foobar-123",
        eigenaar_naam="Dataservices",
        # set to fixed dates to the CSV export can also check for desired formatting
        datum_creatie=date(2021, 1, 3),
        datum_leegmaken=datetime(2021, 1, 3, 12, 13, 14, tzinfo=get_current_timezone()),
        cluster=afval_cluster,
        geometry=Point(123207.6558130105, 486624.6399002579),
    )

    url = "/v1/mvt/afvalwegingen/containers/17/67327/43077.pbf"
    response = api_client.get(url)
    # MVT view returns 204 when the tile is empty.
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [1928, 2558]},
                    "properties": {
                        "id": 1,
                        "clusterId": "c1",  # relation
                        "serienummer": "foobar-123",
                        "datumCreatie": "2021-01-03",
                        "eigenaarNaam": "Dataservices",
                        "datumLeegmaken": "2021-01-03 12:13:14+01",
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }

    # Try again at a higher zoom level. We should get the same features and only the "id" property.
    url = "/v1/mvt/afvalwegingen/containers/14/8415/5384.pbf"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [3825, 1344]},
                    "properties": {
                        "id": 1,
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }

    # MVT view returns 204 when the tile is empty.
    url = "/v1/mvt/afvalwegingen/containers/14/0/0.pbf"
    response = api_client.get(url)
    assert response.status_code == 204
    assert response["Content-Type"] == CONTENT_TYPE
    assert response.content == b""


@pytest.mark.django_db
def test_mvt_content_v1(
    api_client, afval_dataset, filled_router, afval_container_model, afval_cluster
):
    """Prove that the MVT view produces vector tiles."""

    # Coordinates below have been calculated using https://oms.wff.ch/calc.htm
    # and https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/.
    afval_container_model.objects.create(
        id=1,
        serienummer="foobar-123",
        eigenaar_naam="Dataservices",
        # set to fixed dates to the CSV export can also check for desired formatting
        datum_creatie=date(2021, 1, 3),
        datum_leegmaken=datetime(2021, 1, 3, 12, 13, 14, tzinfo=get_current_timezone()),
        cluster=afval_cluster,
        geometry=Point(123207.6558130105, 486624.6399002579),
    )

    url = "/v1/mvt/afvalwegingen/v1/containers/17/67327/43077.pbf"
    response = api_client.get(url)
    # MVT view returns 204 when the tile is empty.
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [1928, 2558]},
                    "properties": {
                        "id": 1,
                        "clusterId": "c1",  # relation
                        "serienummer": "foobar-123",
                        "datumCreatie": "2021-01-03",
                        "eigenaarNaam": "Dataservices",
                        "datumLeegmaken": "2021-01-03 12:13:14+01",
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }

    # Try again at a higher zoom level. We should get the same features and only the "id" property.
    url = "/v1/mvt/afvalwegingen/v1/containers/14/8415/5384.pbf"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [3825, 1344]},
                    "properties": {
                        "id": 1,
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }

    # MVT view returns 204 when the tile is empty.
    url = "/v1/mvt/afvalwegingen/v1/containers/14/0/0.pbf"
    response = api_client.get(url)
    assert response.status_code == 204
    assert response["Content-Type"] == CONTENT_TYPE
    assert response.content == b""


@pytest.mark.django_db
def test_mvt_content_zoom(api_client, gebieden_dataset, buurten_model, filled_router):
    """Prove that the MVT view produces vector tiles with properties at the right zoom
    level."""

    buurten_model.objects.create(
        id="03630000000078",
        identificatie="03630000000078",
        volgnummer=2,
        naam="AAA v2",
        ligt_in_wijk_id="03630012052035.1",
        ligt_in_wijk_identificatie="03630012052035",
        ligt_in_wijk_volgnummer="1",
        geometrie=Point(123207.6558130105, 486624.6399002579),
    )
    # buurten has zoom { min: 12, max: 16 }, so zoom 17 should not show details.
    url = "/v1/mvt/gebieden/buurten/17/67327/43077.pbf"
    response = api_client.get(url)
    # MVT view returns 204 when the tile is empty.
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [1928, 2558]},
                    "properties": {
                        "identificatie": "03630000000078",
                        "volgnummer": 2,
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }

    # Try again at a lower zoom level. We should now get the details.
    url = "/v1/mvt/gebieden/buurten/14/8415/5384.pbf"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == CONTENT_TYPE

    vt = decode_mvt(response)

    assert vt == {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [3825, 1344]},
                    "properties": {
                        "id": "03630000000078",
                        "identificatie": "03630000000078",
                        "volgnummer": 2,
                        "ligtInWijkId": "03630012052035.1",
                        "naam": "AAA v2",
                    },
                    "id": 0,
                    "type": "Feature",
                }
            ],
        }
    }


@pytest.mark.django_db
def test_mvt_forbidden(api_client, geometry_auth_thing, fetch_auth_token, filled_router):
    """Prove that an unauthorized geometry field gives 403 Forbidden"""

    # Get authorization for the meta field, but not the geometry field.
    token = fetch_auth_token(["TEST/META"])

    url = "/v1/mvt/geometry_auth/things/1/0/0.pbf"
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 403


@pytest.mark.django_db
def test_mvt_model_auth(api_client, geometry_auth_model, fetch_auth_token, filled_router):
    """Prove that unauthorized fields are excluded from vector tiles"""
    # See test_mvt_content for how to compute the coordinates.
    geometry_auth_model.objects.create(
        id=1,
        metadata="secret",
        geometry_with_auth=Point(123207.6558130105, 486624.6399002579),
    )

    # We have to zoom in far to get the secret fields in the first place.
    url = "/v1/mvt/geometry_auth/things/17/67327/43077.pbf"
    content = {
        "default": {
            "extent": 4096,
            "version": 2,
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [1928, 2558]},
                    "id": 0,
                    "properties": {"id": 1, "metadata": "secret"},
                    "type": "Feature",
                }
            ],
        }
    }

    # With both required scopes, we get a full response.
    token = fetch_auth_token(["TEST/GEO", "TEST/META"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert decode_mvt(response) == content

    # With only the GEO scope, we still get a 200 response
    # but we lose access to the metadata field.
    token = fetch_auth_token(["TEST/GEO"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200

    del content["default"]["features"][0]["properties"]["metadata"]
    assert decode_mvt(response) == content


def decode_mvt(response: HttpResponseBase) -> bytes:
    if isinstance(response, HttpResponse):
        content = response.content
    elif isinstance(response, StreamingHttpResponse):
        content = b"".join(response.streaming_content)
    else:
        raise TypeError(f"unexpected {type(response)}")
    return mapbox_vector_tile.decode(content)
