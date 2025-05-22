import pytest
from django.db import connection
from django.urls import NoReverseMatch, reverse
from rest_framework.status import HTTP_200_OK
from schematools.contrib.django.db import create_tables

from rest_framework_dso.crs import CRS, RD_NEW
from tests.utils import read_response_json


@pytest.mark.django_db
def test_list_dynamic_view_reload(api_client, api_rf, router, bommen_dataset):
    """Prove that building the router also creates the available viewsets."""
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:bommen-bommen-list")

    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 1

    # Make sure the tables are created too
    if "bommen_bommen" not in connection.introspection.table_names():
        create_tables(bommen_dataset, base_app_name="dso_api.dynamic_api")

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:bommen-bommen-list")

    # Prove that the view is available and works
    response = api_client.get(url)
    data = read_response_json(response)

    assert response.status_code == 200, data
    assert data == {
        "_links": {
            "self": {"href": "http://testserver/v1/bommen/bommen"},
        },
        "_embedded": {"bommen": []},
        "page": {"number": 1, "size": 20},
    }
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"


@pytest.mark.django_db
def test_filled_router(api_client, bommen_dataset, filled_router):
    """Prove that building the router also creates the available viewsets."""
    url = reverse("dynamic_api:bommen-bommen-list")
    response = api_client.get(url)
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_list_dynamic_view_unregister(api_client, bommen_dataset, filled_router):
    """Prove that unregistering works."""
    url = reverse("dynamic_api:bommen-bommen-list")

    # Normal requests give a 200
    response = api_client.get(url)
    assert response.status_code == 200

    # Prove that unloading the model also removes the API from urls.py
    filled_router.clear_urls()
    response = api_client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
class TestDSOViewMixin:
    """Prove that the DSO view mixin logic is used within the dynamic API."""

    def test_not_supported_crs(self, api_client, afval_dataset, filled_router):
        """Prove that invalid CRS leads to a 406 status"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, headers={"Accept-Crs": "EPSG:2000"})
        assert response.status_code == 406, response.data

    def test_bogus_crs(self, api_client, afval_dataset, filled_router):
        """Prove that invalid CRS leads to a 406 status"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        for crs in ("nonsense", "EPSG:", "EPSG:foo"):
            response = api_client.get(url, headers={"Accept-Crs": crs})
            assert response.status_code == 406, response.data

    def test_response_has_crs_from_accept_crs(self, api_client, afval_dataset, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, headers={"Accept-Crs": "EPSG:4258"})
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_accept_crs_empty_data(
        self, api_client, afval_dataset, filled_router
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, headers={"Accept-Crs": "EPSG:4258"})
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_content(self, api_client, afval_container, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header"""
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string(response["Content-Crs"]) == RD_NEW


@pytest.mark.django_db
class TestLimitFields:
    """Test how the ?_fields=... parameter works with all extra serializer weight."""

    @staticmethod
    def test_fields(api_client, afval_dataset, afval_container, filled_router):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, data={"_fields": "id,serienummer"})
        assert response.status_code == HTTP_200_OK, response.data
        data = read_response_json(response)
        assert data["_embedded"] == {
            "containers": [
                {
                    "_links": {
                        # _links block still exists with self link:
                        "self": {
                            "href": "http://testserver/v1/afvalwegingen/containers/1",
                            "id": 1,
                            "title": "1",
                        },
                        "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                    },
                    "id": 1,
                    "serienummer": "foobar-123",
                }
            ]
        }


@pytest.mark.django_db
class TestSort:
    """Prove that the ordering works as expected."""

    @staticmethod
    def test_list_ordering_name(api_client, movies_data, filled_router):
        """Prove that ?_sort=... works on the list view."""

        response = api_client.get("/v1/movies/movie/", data={"_sort": "name"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["foo123", "test"], data

        response = api_client.get("/v1/movies/movie/", data={"_sort": "-name"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"], data

    @staticmethod
    def test_list_ordering_name_old_param(api_client, movies_data, filled_router):
        """Prove that ?_sort=... works on the list view."""

        response = api_client.get("/v1/movies/movie/", data={"sorteer": "-name"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_date(api_client, movies_data, filled_router):
        """Prove that ?_sort=... works on the list view."""
        response = api_client.get("/v1/movies/movie/", data={"_sort": "-dateAdded"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_invalid(api_client, movies_category, django_assert_num_queries):
        """Prove that ?_sort=... only works on a fixed set of fields."""
        response = api_client.get("/v1/movies/movie/", data={"_sort": "foobarvalue"})
        data = read_response_json(response)

        assert response.status_code == 400, data
        assert data == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies/movie/?_sort=foobarvalue",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:invalid",
                    "name": "invalid",
                    "reason": "Field 'foobarvalue' does not exist",
                }
            ],
            "x-validation-errors": ["Field 'foobarvalue' does not exist"],
        }


@pytest.mark.django_db
def test_nested_object_field_response(
    api_client, verblijfsobjecten_model, panden_data, verblijfsobjecten_data, filled_router
):
    """Prove that a nested object fields provides a correct response.

    The nested field will be "flattened", so the subfields will be expanded into the main table.
    """
    url = reverse("dynamic_api:bag-panden-list")
    response = api_client.get(
        url,
        data={"_expand": "true", "id": "0363100012061164.3"},
    )
    data = read_response_json(response)
    assert response.status_code == 200, data
    assert data["_embedded"]["panden"][0]["statusCode"] == 7
    assert data["_embedded"]["panden"][0]["statusOmschrijving"] == "Sloopvergunning verleend"
    assert data["_embedded"]["panden"][0]["bagProces"] == {"code": 1}
