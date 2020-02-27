import time
import pytest
from django.db import connection
from django.urls import reverse
from jwcrypto.jwt import JWT
from authorization_django import jwks

from rest_framework_dso.crs import CRS, RD_NEW
from dso_api.datasets import models
from dso_api.lib.schematools.db import create_tables


@pytest.mark.django_db
def test_list_dynamic_view(api_client, api_rf, router, bommen_dataset):
    """Prove that building the router also creates the available viewsets."""
    assert len(router.urls) == 0, [p.name for p in router.urls]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 0

    # Make sure the tables are created too
    if "bommen_bommen" not in connection.introspection.table_names():
        create_tables(bommen_dataset.schema)

    # Prove that URLs can now be resolved.
    url = reverse("dynamic_api:bommen-bommen-list")

    # Prove that the view is available and works
    response = api_client.get(url)
    assert response.status_code == 200, response.data
    assert response.json() == {
        "_links": {
            "self": {"href": "http://testserver/v1/bommen/bommen/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "count": 0,
        "page_size": 20,
        "_embedded": {"bommen": []},
    }


@pytest.mark.django_db
def test_filled_router(api_client, filled_router):
    """Prove that building the router also creates the available viewsets."""
    url = reverse("dynamic_api:bommen-bommen-list")
    response = api_client.get(url)
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_list_dynamic_view_unregister(api_client, api_rf, filled_router):
    """Prove that unregistering"""
    url = reverse("dynamic_api:bommen-bommen-list")
    viewset = filled_router.registry[0][1]

    # Normal requests give a 200
    response = api_client.get(url)
    assert response.status_code == 200

    # Prove that unloading the model also removes the API from urls.py
    filled_router.clear_urls()
    response = api_client.get(url)
    assert response.status_code == 404

    # Prove that if any requests to the viewset were still pending,
    # they also return a 404 now. This means they passed the URL resolving,
    # but were paused during the read-lock.
    request = api_rf.get(url)
    view = viewset.as_view({"get": "list"})
    response = view(request)
    assert response.status_code == 404, response.data


@pytest.mark.django_db
class TestDSOViewMixin:
    """Prove that the DSO view mixin logic is used within the dynamic API."""

    def test_not_supported_crs(self, api_client, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:2000")
        assert response.status_code == 406, response.data

    def test_bogus_crs(self, api_client, filled_router):
        """Prove that invalid CRS leads to a 406 status """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="nonsense")
        assert response.status_code == 406, response.data

    def test_response_has_crs_from_accept_crs(self, api_client, filled_router):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_accept_crs_empty_data(
        self, api_client, filled_router
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url, HTTP_ACCEPT_CRS="EPSG:4258")
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert CRS.from_string("EPSG:4258") == CRS.from_string(response["Content-Crs"])

    def test_response_has_crs_from_content(
        self, api_client, filled_router, afval_container
    ):
        """Prove that response has a CRS header taken from the Accept-Crs header """
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        response = api_client.get(url)
        assert response.status_code == 200, response.data
        assert response.has_header("Content-Crs"), dict(response.items())
        assert RD_NEW == CRS.from_string(response["Content-Crs"])


@pytest.fixture
def tokendata_correct():
    now = int(time.time())
    return {
        "iat": now,
        "exp": now + 30,
        "scopes": ["BAG/R"],
        "sub": "test@tester.nl",
    }


def create_token(tokendata, alg):
    kid = "2aedafba-8170-4064-b704-ce92b7c89cc6"
    key = jwks.get_keyset().get_key(kid)
    token = JWT(header={"alg": alg, "kid": kid}, claims=tokendata)
    token.make_signed_token(key)
    return token


@pytest.mark.django_db
class TestAuth:
    """ Test authorization """

    def test_auth_on_dataset_schema_protects_endpoint(
        self, api_client, filled_router, afval_schema
    ):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.Dataset.objects.filter(name="afval").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_protects_endpoint(
        self, api_client, filled_router, afval_schema
    ):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        response = api_client.get(url)
        assert response.status_code == 403, response.data

    def test_auth_on_table_schema_with_token(
        self, api_client, filled_router, afval_schema, tokendata_correct
    ):
        url = reverse("dynamic_api:afvalwegingen-containers-list")
        models.DatasetTable.objects.filter(name="containers").update(auth="BAG/R")
        token = create_token(tokendata_correct, "ES256").serialize()
        response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
        assert response.status_code == 200, response.data
