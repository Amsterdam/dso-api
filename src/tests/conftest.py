import time
import json
from datetime import date
from pathlib import Path

import pytest
from jwcrypto.jwt import JWT
from django.db import connection
from django.utils.timezone import now
from django.contrib.gis.geos import GEOSGeometry, Point
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from authorization_django import jwks

from dso_api.datasets.models import Dataset
from dso_api.lib.schematools.db import create_tables
from amsterdam_schema.types import DatasetSchema
from rest_framework_dso.crs import RD_NEW
from tests.test_rest_framework_dso.models import Category, Movie, Location

HERE = Path(__file__).parent


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()


@pytest.fixture()
def api_request(api_rf) -> Request:
    """Return a very basic Request object that's good enough as serializer context."""
    request = api_rf.get("/v1/dummy/")
    request.accept_crs = None  # for DSOSerializer, expects to be used with DSOViewMixin
    request.response_content_crs = None
    return request


@pytest.fixture()
def api_client() -> APIClient:
    """Return a client that has unhindered access to the API views"""
    return APIClient()


@pytest.fixture()
def router():
    """Provide the router import as fixture.

    It can't be imported directly as urls.py accesses the database.
    The fixture also restores the application URL patterns after the test completed.
    """
    from dso_api.dynamic_api.urls import router

    assert (
        not router.registry
    ), "DynamicRouter already has URL patterns before test starts!"

    yield router

    # Only any changes that tests may have done to the router
    if router.registry:
        router.clear_urls()


@pytest.fixture()
def filled_router(router, afval_dataset, bommen_dataset):
    # Prove that the router URLs are extended on adding a model
    router.reload()
    router_urls = [p.name for p in router.urls]
    assert len(router_urls) > 1, router_urls

    # Make sure the tables are created too
    table_names = connection.introspection.table_names()
    if "afval_containers" not in table_names:
        create_tables(afval_dataset.schema)
    if "bommen_bommen" not in table_names:
        create_tables(bommen_dataset.schema)

    return router


@pytest.fixture()
def afval_schema_json() -> dict:
    path = HERE / "files/afval.json"
    return json.loads(path.read_text())


@pytest.fixture()
def afval_schema(afval_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(afval_schema_json)


@pytest.fixture()
def afval_dataset(afval_schema_json) -> Dataset:
    return Dataset.objects.create(name="afval", schema_data=afval_schema_json)


@pytest.fixture()
def afval_cluster_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["afvalwegingen"]["clusters"]


@pytest.fixture()
def afval_cluster(afval_cluster_model):
    return afval_cluster_model.objects.create(id="c1", status="valid")


@pytest.fixture()
def afval_container_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["afvalwegingen"]["containers"]


@pytest.fixture()
def afval_container(afval_container_model, afval_cluster):
    return afval_container_model.objects.create(
        id=1,
        serienummer="foobar-123",
        eigenaar_naam="Dataservices",
        datum_creatie=date.today(),
        datum_leegmaken=now(),
        cluster=afval_cluster,
        geometry=Point(10, 10),  # no SRID on purpose, should use django model field.
    )


@pytest.fixture()
def bommen_schema_json() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/bommen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bommen_schema(bommen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(bommen_schema_json)


@pytest.fixture()
def bommen_dataset(bommen_schema_json) -> Dataset:
    return Dataset.objects.create(name="bommen", schema_data=bommen_schema_json)


@pytest.fixture
def category() -> Category:
    """A dummy model to test our API with"""
    return Category.objects.create(name="bar")


@pytest.fixture
def movie(category) -> Movie:
    """A dummy model to test our API with"""
    return Movie.objects.create(name="foo123", category=category)


@pytest.fixture
def location() -> Location:
    """A dummy model to test our API with"""
    return Location.objects.create(geometry=GEOSGeometry("Point(10 10)", srid=RD_NEW))


@pytest.fixture
def fetch_tokendata():
    """ Fixture to create valid token data, scopes is flexible """

    def _fetcher(scopes):
        now = int(time.time())
        return {
            "iat": now,
            "exp": now + 30,
            "scopes": scopes,
            "sub": "test@tester.nl",
        }

    return _fetcher


@pytest.fixture
def fetch_auth_token(fetch_tokendata):
    """ Fixture to create an auth token, scopes is flexible """

    def _fetcher(scopes):
        kid = "2aedafba-8170-4064-b704-ce92b7c89cc6"
        key = jwks.get_keyset().get_key(kid)
        token = JWT(header={"alg": "ES256", "kid": kid}, claims=fetch_tokendata(scopes))
        token.make_signed_token(key)
        return token.serialize()

    return _fetcher
