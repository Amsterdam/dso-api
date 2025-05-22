import inspect
import json
from typing import Any

import orjson
import pytest
from django.urls import reverse
from rest_framework.response import Response

from rest_framework_dso.response import StreamingResponse
from tests.conftest import DAM_SQUARE_POINT
from tests.utils import patch_table_auth, read_response, read_response_json

RAW_GEOJSON_COORDS = list(DAM_SQUARE_POINT.transform("urn:ogc:def:crs:OGC::CRS84", clone=True))

# allow minor differences in comparing the floats. This makes sure that the
# precise float deserialization of orjson.loads() doesn't cause any
# comparison issues. The first 14 decimals must be the same:
GEOJSON_COORDS = pytest.approx(RAW_GEOJSON_COORDS, rel=1e-14, abs=1e-14)


def as_is(data):
    return data


@pytest.mark.django_db
class TestFormats:
    """Prove that common rendering formats work as expected"""

    def test_point_crs84(self):
        """See that our GEOJSON_POINT uses the correct axis ordering.
        This only compares a rounded version, as there can be subtle differences
        in the actual value depending on your GDAL/libproj version.
        """
        crs84_point = pytest.approx(RAW_GEOJSON_COORDS, rel=1e-2)
        # GeoJSON should always be longitude and latitude,
        # even though GDAL 2 vs 3 have different behavior:
        # https://gdal.org/tutorials/osr_api_tut.html#crs-and-axis-order
        assert crs84_point == [4.89, 52.37]

    UNPAGINATED_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            b"1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992;"
            b"POINT (121389 487369)\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "FeatureCollection",
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
                    "type": "name",
                },
                "features": [
                    {
                        "type": "Feature",
                        "id": "containers.1",
                        "geometry": {
                            "type": "Point",
                            "coordinates": GEOJSON_COORDS,
                        },
                        "properties": {
                            "id": 1,
                            "clusterId": "c1",
                            "serienummer": "foobar-123",
                            "eigenaarNaam": "Dataservices",
                            "datumCreatie": "2021-01-03",
                            "datumLeegmaken": "2021-01-03T12:13:14",
                        },
                    }
                ],
                "_links": [],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(UNPAGINATED_FORMATS.keys()))
    def test_unpaginated_list(self, format, api_client, afval_container, filled_router):
        """Prove that the export formats generate proper data."""
        decoder, expected_type, expected_data = self.UNPAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading
        assert response["Content-Disposition"].startswith(
            'attachment; filename="afvalwegingen-containers'
        )

        # Paginator was not triggered
        assert "X-Pagination-Page" not in response
        assert "X-Pagination-Limit" not in response
        assert "X-Pagination-Count" not in response
        assert "X-Total-Count" not in response

        # proves middleware detected streaming response, and didn't break it:
        assert "Content-Length" not in response

        # Check that the response is streaming:
        assert response.streaming
        assert inspect.isgeneratorfunction(response.accepted_renderer.render)

    PAGE_SIZE = 4

    def _make_csv_page(self, page_num: int, page_size_param: str) -> Any:
        start = 1 + (page_num - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE

        lines = (
            f"{i},c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,"
            "SRID=28992;POINT (121389 487369)\r\n"
            for i in range(start, end)
        )
        return (
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            + b"".join(line.encode("ascii") for line in lines)
        )

    def _make_json_page(self, page_num: int, page_size_param: str) -> Any:
        start = 1 + (page_num - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE

        cluster = {
            "href": ("http://testserver/v1/afvalwegingen/clusters/c1?_format=json"),
            "id": "c1",
            "title": "c1",
        }
        schema = "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers"

        page = {
            "_embedded": {
                "containers": [
                    {
                        "_links": {
                            "cluster": cluster,
                            "schema": schema,
                            "self": {
                                "href": f"http://testserver/v1/afvalwegingen/containers/{i}?_format=json",
                                "id": i,
                                "title": str(i),
                            },
                        },
                        "clusterId": "c1",
                        "datumCreatie": "2021-01-03",
                        "datumLeegmaken": "2021-01-03T12:13:14",
                        "eigenaarNaam": "Dataservices",
                        "geometry": {"coordinates": [121389, 487369], "type": "Point"},
                        "id": i,
                        "serienummer": "foobar-123",
                    }
                    for i in range(start, end)
                ]
            },
            "_links": {
                "next": {
                    # TODO we may want to always output _pageSize.
                    "href": "http://testserver/v1/afvalwegingen/containers?_format=json"
                    + "".join(
                        sorted([f"&{page_size_param}={self.PAGE_SIZE}", f"&page={page_num+1}"])
                    )
                },
                "self": {
                    "href": f"http://testserver/v1/afvalwegingen/containers?_format=json&{page_size_param}={self.PAGE_SIZE}&page={page_num}"
                },
            },
            "page": {"number": page_num, "size": self.PAGE_SIZE},
        }

        if page_num > 1:
            page["_links"]["previous"] = {
                "href": f"http://testserver/v1/afvalwegingen/containers?_format=json&{page_size_param}={self.PAGE_SIZE}"
            }

        return page

    def _make_geojson_page(self, page_num: int, page_size_param: str):
        start = 1 + (page_num - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE

        page = {
            "type": "FeatureCollection",
            "crs": {
                "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
                "type": "name",
            },
            "features": [
                {
                    "type": "Feature",
                    "id": f"containers.{i}",
                    "geometry": {
                        "type": "Point",
                        "coordinates": GEOJSON_COORDS,
                    },
                    "properties": {
                        "id": i,
                        "clusterId": "c1",
                        "serienummer": "foobar-123",
                        "datumCreatie": "2021-01-03",
                        "eigenaarNaam": "Dataservices",
                        "datumLeegmaken": "2021-01-03T12:13:14",
                    },
                }
                for i in range(start, end)
            ],
            "_links": [
                {
                    "rel": "next",
                    "type": "application/geo+json",
                    "title": "next page",
                    "href": "http://testserver/v1/afvalwegingen/containers"
                    f"?_format=geojson&_pageSize=4&page={page_num+1}",
                },
            ],
        }

        if page_num > 1:
            page["_links"].append(
                {
                    "rel": "previous",
                    "type": "application/geo+json",
                    "title": "previous page",
                    "href": "http://testserver/v1/afvalwegingen/containers"
                    "?_format=geojson&_pageSize=4",
                },
            )

        return page

    PAGINATED_FORMATS = {
        # "csv": (b''.join, "text/csv; charset=utf-8", _make_csv_page),
        "csv": (as_is, "text/csv; charset=utf-8", _make_csv_page),
        "json": (orjson.loads, "application/hal+json", _make_json_page),
        "geojson": (orjson.loads, "application/geo+json; charset=utf-8", _make_geojson_page),
    }

    @pytest.mark.parametrize("format", sorted(PAGINATED_FORMATS.keys()))
    @pytest.mark.parametrize("page_num", (1, 2))
    @pytest.mark.parametrize("page_size_param", ["_pageSize", "page_size"])
    def test_paginated_list(
        self,
        fetch_auth_token,
        format,
        page_num,
        page_size_param,
        api_client,
        afval_container,
        filled_router,
    ):
        """Prove that the pagination still works if explicitly requested."""
        decoder, expected_type, make_expected = self.PAGINATED_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        for i in range(2, 10):
            afval_container.id = i
            afval_container.save()

        # Prove that the view is available and works
        token = fetch_auth_token(["BAG/R"])  # needed in afval.json to fetch cluster
        response = api_client.get(
            url,
            {"_format": format, page_size_param: self.PAGE_SIZE, "page": page_num},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert response["Content-Type"] == expected_type  # And test after reading

        if format != "json" and page_size_param == "page_size":
            pytest.xfail("Handling of this synonym is broken: AB#24678.")

        # Paginator was triggered
        assert response["X-Pagination-Page"] == str(page_num)
        assert response["X-Pagination-Limit"] == "4"

        assert data == make_expected(self, page_num, page_size_param)

        # proves middleware detected streaming response, and didn't break it:
        assert "Content-Length" not in response

        # Check that the response is streaming:
        assert response.streaming
        assert inspect.isgeneratorfunction(response.accepted_renderer.render)

    EMPTY_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "FeatureCollection",
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
                    "type": "name",
                },
                "features": [],
                "_links": [],
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(EMPTY_FORMATS.keys()))
    def test_empty_list(self, format, api_client, afval_dataset, filled_router):
        """Prove that empty list pages are properly serialized."""
        decoder, expected_type, expected_data = self.EMPTY_FORMATS[format]
        url = reverse("dynamic_api:afvalwegingen-containers-list")

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

    def test_csv_expand_inline(
        self, api_client, api_rf, afval_container, fetch_auth_token, filled_router
    ):
        """Prove that the expand logic works, which is implemented inline for CSV"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        token = fetch_auth_token(["BAG/R"])  # needed in afval.json to fetch cluster
        response = api_client.get(
            url,
            {"_format": "csv", "_expandScope": "cluster"},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert response["Content-Type"] == "text/csv; charset=utf-8"  # Test before reading stream
        assert response["Content-Disposition"].startswith(
            'attachment; filename="afvalwegingen-containers'
        )

        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = read_response(response)
        assert data == (
            "Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken"
            ",Geometry,Cluster.Id,Cluster.Status\r\n"
            "1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14"
            ",SRID=28992;POINT (121389 487369),c1,valid\r\n"
        )

    def test_csv_expand_m2m_invalid(self, api_client, api_rf, ggwgebieden_data, filled_router):
        """Prove that the expand logic works, which is implemented inline for CSV"""
        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        api_client.raise_request_exception = False
        response = api_client.get(url, {"_format": "csv", "_expandScope": "bestaatUitBuurten"})
        assert response.status_code == 400, response.getvalue()
        data = read_response_json(response)
        assert data == {
            "detail": (
                "Eager loading is not supported for field 'bestaatUitBuurten' "
                "in this output format"
            ),
            "status": 400,
            "title": "Malformed request.",
            "type": "urn:apiexception:parse_error",
        }

    def test_csv_expand_skip_m2m(self, api_client, api_rf, ggwgebieden_data, filled_router):
        """Prove that the expand logic works, but skips M2M relations for auto-expand-all"""
        url = reverse("dynamic_api:gebieden-ggwgebieden-list")
        api_client.raise_request_exception = False
        response = api_client.get(url, {"_format": "csv", "_expand": "true"})
        assert response.status_code == 200, response.getvalue()
        data = read_response(response)

        # fields don't include bestaatUitBuurten
        assert data == (
            "Identificatie,Volgnummer,Registratiedatum,Naam,Begingeldigheid,Eindgeldigheid,"
            "Geometrie\r\n"
            "03630950000000,1,,,2021-02-28,,\r\n"
        )

    def test_csv_array_fields(self, api_client, api_rf, fietspaaltjes_data):
        url = reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")
        api_client.raise_request_exception = False
        response = api_client.get(url, {"_format": "csv"})
        assert response.status_code == 200, response.getvalue()
        data = read_response(response)

        assert data == (
            "Id,Geometry,Street,At,Area,Score2013,Scorecurrent,Count,Paaltjesweg,Soortpaaltje"
            ",Uiterlijk,Type,Ruimte,Markering,Beschadigingen,Veiligheid,Zichtindonker,Soortweg,Noodzaak\r\n"
            "Fietsplaatje record met display"
            ",SRID=28992;POINT (123207.6558130105 486624.6399002579)"
            ",Weesperplein,Geschutswerf,Amsterdam-Centrum,,reference for DISPLAY FIELD,6"
            ",nu paaltje(s)"  # paaltjes_weg: 1 item
            ',"paaltje(s) ong. 75cm hoog,verwijderde paaltjes"'  # soort_paaltje: array of 2
            ",rood/wit"  # uiterlijk
            ',"vast,uitneembaar"'  # type, array of 2
            ",Voldoende: 1.6m of meer"  # ruimte, 1 item
            ',"markering ontbreekt,onvoldoende markering"'  # markering: array of 2
            ",,overzichtelijke locatie,onvoldoende reflectie op paal"
            ',"rijbaan fiets+auto,fietspad"'  # soort_weg: array of 2
            ",nodig tegen sluipverkeer\r\n"  # noodzaak: 1 item
        )

    DETAIL_FORMATS = {
        "csv": (
            as_is,
            "text/csv; charset=utf-8",
            b"Id,Clusterid,Serienummer,Eigenaarnaam,Datumcreatie,Datumleegmaken,Geometry\r\n"
            b"1,c1,foobar-123,Dataservices,2021-01-03,2021-01-03T12:13:14,SRID=28992"
            b";POINT (121389 487369)\r\n",
        ),
        "geojson": (
            orjson.loads,
            "application/geo+json; charset=utf-8",
            {
                "type": "Feature",
                "id": "containers.1",
                "geometry": {
                    "coordinates": GEOJSON_COORDS,
                    "type": "Point",
                },
                "properties": {
                    "id": 1,
                    "clusterId": "c1",
                    "serienummer": "foobar-123",
                    "eigenaarNaam": "Dataservices",
                    "datumCreatie": "2021-01-03",
                    "datumLeegmaken": "2021-01-03T12:13:14",
                },
                "crs": {
                    "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
                    "type": "name",
                },
            },
        ),
    }

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail(self, format, api_client, afval_schema, afval_container, filled_router):
        """Prove that the detail view also returns an export of a single feature."""
        decoder, expected_type, expected_data = self.DETAIL_FORMATS[format]
        patch_table_auth(afval_schema, "clusters", auth=["OPENBAAR"])
        url = reverse(
            "dynamic_api:afvalwegingen-containers-detail",
            kwargs={"pk": afval_container.pk},
        )

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert response["Content-Type"] == expected_type  # Test before reading stream
        assert response.status_code == 200, response.getvalue()
        assert isinstance(response, StreamingResponse)
        data = decoder(response.getvalue())
        assert data == expected_data
        assert response["Content-Type"] == expected_type  # And test after reading

        # Paginator was NOT triggered
        assert "X-Pagination-Page" not in response

    @pytest.mark.parametrize("format", sorted(DETAIL_FORMATS.keys()))
    def test_detail_404(self, format, api_client, afval_dataset, filled_router):
        """Prove that error pages are also properly rendered.
        These are not rendered in the output format, but get a generic exception.
        """
        url = reverse(
            "dynamic_api:afvalwegingen-containers-detail",
            kwargs={"pk": 9999999999},
        )

        # Prove that the view is available and works
        response = api_client.get(url, {"_format": format})
        assert isinstance(response, Response)  # still wrapped in DRF response!
        assert response.status_code == 404, response.getvalue()
        assert response["Content-Type"] == "application/problem+json"
        data = json.loads(response.getvalue())
        assert data == {
            "type": "urn:apiexception:not_found",
            "title": "Not found.",
            "detail": "No Containers found matching the query",
            "status": 404,
        }

        # Paginator was NOT triggered
        assert "X-Pagination-Page" not in response

    @pytest.mark.parametrize("format", sorted(PAGINATED_FORMATS.keys()))
    def test_list_count_true(self, api_client, afval_container, filled_router, format):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        # triger pagination with _pageSize
        response = api_client.get(
            url, data={"_count": "true", "_format": format, "_pageSize": 1000}
        )

        assert response.status_code == 200, response.getvalue()
        assert response["X-Pagination-Count"] == "1"
        assert response["X-Total-Count"] == "1"

    @pytest.mark.parametrize("format", sorted(PAGINATED_FORMATS.keys()))
    @pytest.mark.parametrize("data", [{}, {"_count": "false"}, {"_count": "0"}, {"_count": "1"}])
    def test_list_count_false(self, api_client, bommen_dataset, filled_router, data, format):
        url = reverse("dynamic_api:bommen-bommen-list")
        # trigger pagination with _pageSize but dont count
        response = api_client.get(url, data=data | {"_format": format, "_pageSize": 1000})

        assert response.status_code == 200, response.getvalue()
        assert "X-Total-Count" not in response
        assert "X-Pagination-Count" not in response

    def test_csv_exclude_field(self, api_client, gebieden_dataset, filled_router):
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(
            url, {"_format": "csv", "_fields": "-code,-naam,-documentdatum,-documentnummer"}
        )
        assert response.status_code == 200
        response_data = [row.decode("utf-8") for row in response.streaming_content]
        assert response_data == [
            "Identificatie,Volgnummer,Registratiedatum,Begingeldigheid,Eindgeldigheid,"
            "Ligtingemeenteidentificatie,Geometrie\r\n"
        ]

    def test_csv_exclude_include_400(self, api_client, gebieden_dataset, filled_router):
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url, {"_format": "csv", "_fields": "-code,naam"})
        assert response.status_code == 400
        assert "invalid-params" in response.data
        assert (
            response.data["invalid-params"][0]["reason"]
            == "It's not possible to combine inclusions and exclusions in the _fields parameter"
        )

    @pytest.mark.parametrize(
        "fields,data",
        [
            ("naam,volgnummer,code", ["Naam,Volgnummer,Code\r\n"]),
            ("volgnummer,code,naam", ["Volgnummer,Code,Naam\r\n"]),
        ],
    )
    def test_csv_ordered_fields(self, api_client, gebieden_dataset, filled_router, fields, data):
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url, {"_format": "csv", "_fields": fields})
        assert response.status_code == 200
        response_data = [row.decode("utf-8") for row in response.streaming_content]
        assert response_data == data

    @pytest.mark.parametrize(
        "fields,data",
        [
            ("naam,volgnummer,code", ["Naam,Volgnummer,Code\r\nCentrum,1,A\r\n"]),
            ("volgnummer,code,naam", ["Volgnummer,Code,Naam\r\n1,A,Centrum\r\n"]),
        ],
    )
    def test_csv_ordered_fields_with_data(
        self, api_client, stadsdelen_data, filled_router, fields, data
    ):
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url, {"_format": "csv", "_fields": fields})
        assert response.status_code == 200
        response_data = [row.decode("utf-8") for row in response.streaming_content]
        assert response_data == data

    @pytest.mark.parametrize(
        "fields,data",
        [
            (
                "naam,ligtInGemeente.identificatie,code",
                ["Naam,ligtInGemeente.identificatie,Code\r\n"],
            ),
            (
                "ligtInGemeente.identificatie,code,naam",
                ["ligtInGemeente.identificatie,Code,Naam\r\n"],
            ),
        ],
    )
    def test_csv_ordered_fields_embedded(
        self, api_client, gebieden_dataset, filled_router, fields, data
    ):
        url = reverse("dynamic_api:gebieden-stadsdelen-list")
        response = api_client.get(url, {"_format": "csv", "_fields": fields, "_expand": "true"})
        assert response.status_code == 200
        response_data = [row.decode("utf-8") for row in response.streaming_content]
        assert response_data == data

    @pytest.mark.parametrize(
        "fields,data",
        [
            (
                "naam,ligtInStadsdeel.naam,volgnummer",
                ["Naam,Ligtinstadsdeel.Naam,Volgnummer\r\nBurgwallen-Nieuwe Zijde,Centrum,1\r\n"],
            ),
            (
                "ligtInStadsdeel.naam,volgnummer,naam",
                ["Ligtinstadsdeel.Naam,Volgnummer,Naam\r\nCentrum,1,Burgwallen-Nieuwe Zijde\r\n"],
            ),
        ],
    )
    def test_csv_ordered_fields_embedded_with_data(
        self,
        api_client,
        stadsdelen_data,
        wijken_data,
        filled_router,
        fields,
        data,
    ):
        url = reverse("dynamic_api:gebieden-wijken-list")
        response = api_client.get(url, {"_format": "csv", "_fields": fields, "_expand": "true"})
        assert response.status_code == 200
        response_data = [row.decode("utf-8") for row in response.streaming_content]
        assert response_data == data

    @pytest.mark.parametrize(
        "accept_crs",
        ["urn:ogc:def:crs:OGC::CRS84", "urn:ogc:def:crs:EPSG::4326", "EPSG:4326"],
    )
    def test_geojson_axis_orientation(
        self, api_client, fietspaaltjes_data, filled_router, accept_crs
    ):
        """Prove that GeoJSON coordinates are properly translated as X,Y.
        The GeoJSON standard mandates that coordinates are always rendered as X,Y.
        That means longitude/latitude (x/y) of CRS84,
        instead of latitude/longitude (y/x) that WGS84 uses (northing/easting).
        """
        url = reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")
        response = api_client.get(url, {"_format": "geojson"}, headers={"Accept-Crs": accept_crs})
        assert response.status_code == 200, response.getvalue()
        data = read_response_json(response)

        assert data["features"][0]["geometry"] == {
            "type": "Point",
            "coordinates": [
                pytest.approx(4.9204, rel=1e-4),  # longitude first!
                pytest.approx(52.3665, rel=1e-4),
            ],
        }
        assert data["crs"] == {
            # To be clear that coordinates are x,y, this format is returned:
            "properties": {"name": "urn:ogc:def:crs:OGC::CRS84"},
            "type": "name",
        }

    def test_rest_api_axis_orientation(self, api_client, fietspaaltjes_data, filled_router):
        """Prove that REST coordinates are properly translated as Y,X for EPSG:4326.
        That follows the EPSG axis ordering.
        This is different from GeoJSON, which mandates x,y ordering.
        """
        url = reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")
        response = api_client.get(url, {"_format": "json"}, headers={"Accept-Crs": "EPSG:4326"})
        assert response.status_code == 200, response.getvalue()
        data = read_response_json(response)

        assert data["_embedded"]["fietspaaltjes"][0]["geometry"] == {
            "type": "Point",
            "coordinates": [
                pytest.approx(52.3665, rel=1e-4),  # longitude first
                pytest.approx(4.9204, rel=1e-4),
            ],
        }
        assert response.headers["Content-Crs"] == "urn:ogc:def:crs:EPSG::4326"

    def test_rest_api_axis_orientation_crs84(self, api_client, fietspaaltjes_data, filled_router):
        """Prove that REST coordinates are properly translated as X,Y when requesting CRS84.
        That is the GeoJSON ordering.
        """
        url = reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")
        response = api_client.get(
            url, {"_format": "json"}, headers={"Accept-Crs": "urn:ogc:def:crs:OGC::CRS84"}
        )
        assert response.status_code == 200, response.getvalue()
        data = read_response_json(response)

        assert data["_embedded"]["fietspaaltjes"][0]["geometry"] == {
            "type": "Point",
            "coordinates": [
                pytest.approx(4.9204, rel=1e-4),  # longitude first (as CRS84 is)
                pytest.approx(52.3665, rel=1e-4),
            ],
        }
        assert response.headers["Content-Crs"] == "urn:ogc:def:crs:OGC::CRS84"
