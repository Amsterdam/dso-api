import time
import json
from datetime import date
from pathlib import Path
from unittest import mock

import pytest
from jwcrypto.jwt import JWT
from django.core.handlers.wsgi import WSGIRequest
from django.db import connection
from django.utils.timezone import now
from django.contrib.gis.geos import GEOSGeometry, Point
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from authorization_django import jwks

from schematools.contrib.django.models import Dataset, Profile
from schematools.contrib.django.db import create_tables
from schematools.contrib.django.auth_backend import RequestProfile
from schematools.types import DatasetSchema, ProfileSchema

from rest_framework_dso.crs import RD_NEW
from tests.test_rest_framework_dso.models import (
    Category,
    Movie,
    Location,
)

HERE = Path(__file__).parent


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()


@pytest.fixture()
def api_request(api_rf) -> WSGIRequest:
    """Return a very basic Request object. This can be used for the APIClient.
    The DRF views use a different request object internally, see `drf_request` for that.
    """
    request = api_rf.get("/v1/dummy/")
    request.accept_crs = None  # for DSOSerializer, expects to be used with DSOViewMixin
    request.response_content_crs = None

    request.user = mock.MagicMock()

    request.auth_profile = RequestProfile(request)

    # Temporal modifications. Usually done via TemporalDatasetMiddleware
    request.versioned = False
    return request


@pytest.fixture()
def drf_request(api_request) -> Request:
    """The wrapped WSGI Request as a Django-Rest-Framework request.
    This is the 'request' object that APIView.dispatch() creates.
    """
    return Request(api_request)


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
        not router.registry or router.registry == router.static_routes
    ), "DynamicRouter already has URL patterns before test starts!"

    yield router

    # Only any changes that tests may have done to the router
    if router.registry:
        router.clear_urls()


@pytest.fixture()
def filled_router(
    router,
    afval_dataset,
    bommen_dataset,
    parkeervakken_dataset,
    bagh_dataset,
    vestiging_dataset,
    fietspaaltjes_dataset,
    fietspaaltjes_dataset_no_display,
    explosieven_dataset,
    indirect_self_ref_dataset,
    download_url_dataset,
    meldingen_dataset,
    gebieden_dataset,
    woningbouwplannen_dataset,
):
    # Prove that the router URLs are extended on adding a model
    router.reload()
    router_urls = [p.name for p in router.urls]
    assert len(router_urls) > 1, router_urls

    # Make sure the tables are created too
    table_names = connection.introspection.table_names()

    datasets = {
        afval_dataset: "afval_containers",
        bommen_dataset: "bommen_bommen",
        parkeervakken_dataset: "parkeervakken_parkeervakken",
        bagh_dataset: "bagh_buurt",
        vestiging_dataset: "vestiging_vestiging",
        fietspaaltjes_dataset: "fietsplaatjes_fietsplaatjes",
        fietspaaltjes_dataset_no_display: "fietspaaltjesnodisplay_fietspaaltjesnodisplay",
        explosieven_dataset: "explosieven_verdachtgebied",
        indirect_self_ref_dataset: "selfref_selfref",
        download_url_dataset: "download_url",
        meldingen_dataset: "meldingen_statistieken",
        gebieden_dataset: "gebieden_buurten",
        woningbouwplannen_dataset: "woningbouwplannen_woningbouwplan",
    }

    # Based on datasets, create test table if not exists
    for dataset, table in datasets.items():
        if table not in table_names:
            create_tables(dataset.schema)
    return router


@pytest.fixture()
def reloadrouter(filled_router):
    """The filled_router, but reloaded before being used.
    this is the Nick-trick :-)  Needed when schemas
    with relations are used.
    """
    filled_router.reload()
    return filled_router


@pytest.fixture()
def afval_schema_json() -> dict:
    path = HERE / "files/afval.json"
    return json.loads(path.read_text())


@pytest.fixture()
def afval_schema_backwards_embedded_json() -> dict:
    path = HERE / "files/afval_backwards_embedded.json"
    return json.loads(path.read_text())


@pytest.fixture()
def afval_schema_backwards_summary_json() -> dict:
    path = HERE / "files/afval_backwards_summary.json"
    return json.loads(path.read_text())


@pytest.fixture()
def afval_schema(afval_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(afval_schema_json)


@pytest.fixture()
def afval_schema_backwards_embedded(
    afval_schema_backwards_embedded_json,
) -> DatasetSchema:
    return DatasetSchema.from_dict(afval_schema_backwards_embedded_json)


@pytest.fixture()
def afval_schema_backwards_summary(
    afval_schema_backwards_summary_json,
) -> DatasetSchema:
    return DatasetSchema.from_dict(afval_schema_backwards_summary_json)


@pytest.fixture()
def afval_dataset(afval_schema_json) -> Dataset:
    return Dataset.objects.create(name="afvalwegingen", schema_data=afval_schema_json)


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


@pytest.fixture()
def brp_schema_json() -> dict:
    """Fixture for the BRP dataset"""
    path = HERE / "files/brp.json"
    return json.loads(path.read_text())


@pytest.fixture()
def brp_schema(brp_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(brp_schema_json)


@pytest.fixture()
def brp_endpoint_url() -> str:
    return "http://remote-server/unittest/brp/ingeschrevenpersonen/"


@pytest.fixture()
def brp_dataset(brp_schema_json, brp_endpoint_url) -> Dataset:
    """Create a remote dataset."""
    return Dataset.objects.create(
        name="brp",
        schema_data=brp_schema_json,
        enable_db=False,
        endpoint_url=brp_endpoint_url,
        url_prefix="remote",
    )


@pytest.fixture
def category() -> Category:
    """A dummy model to test our API with"""
    return Category.objects.create(pk=1, name="bar")


@pytest.fixture
def movie(category) -> Movie:
    """A dummy model to test our API with"""
    return Movie.objects.create(name="foo123", category=category)


@pytest.fixture
def location() -> Location:
    """A dummy model to test our API with"""
    return Location.objects.create(geometry=GEOSGeometry("Point(10 10)", srid=RD_NEW))


@pytest.fixture()
def parkeervakken_schema_json() -> dict():
    path = HERE / "files/parkeervakken.json"
    return json.loads(path.read_text())


@pytest.fixture()
def parkeervakken_schema(parkeervakken_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(parkeervakken_schema_json)


@pytest.fixture()
def parkeervakken_dataset(parkeervakken_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="parkeervakken", schema_data=parkeervakken_schema_json
    )


@pytest.fixture()
def parkeervakken_parkeervak_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["parkeervakken"]["parkeervakken"]


@pytest.fixture()
def parkeervakken_regime_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["parkeervakken"]["parkeervakken_regimes"]


@pytest.fixture()
def bagh_schema_json() -> dict():
    path = HERE / "files/bagh.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bagh_schema(bagh_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(bagh_schema_json)


@pytest.fixture()
def bagh_dataset(bagh_schema_json) -> Dataset:
    return Dataset.objects.create(name="bagh", schema_data=bagh_schema_json)


@pytest.fixture()
def bagh_models(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["bagh"]


@pytest.fixture()
def bagh_gemeente_model(bagh_models):
    return bagh_models["gemeente"]


@pytest.fixture()
def bagh_stadsdeel_model(bagh_models):
    return bagh_models["stadsdeel"]


@pytest.fixture()
def bagh_wijk_model(bagh_models):
    return bagh_models["wijk"]


@pytest.fixture()
def bagh_buurt_model(bagh_models):
    return bagh_models["buurt"]


@pytest.fixture()
def bagh_gemeente(bagh_gemeente_model):
    return bagh_gemeente_model.objects.create(
        naam="Amsterdam", id="0363_001", identificatie="0363", volgnummer=1
    )


@pytest.fixture()
def bagh_stadsdeel(bagh_stadsdeel_model, bagh_gemeente):
    return bagh_stadsdeel_model.objects.create(
        id="03630000000001_001",
        code="H",
        naam="Bos en Lommer",
        gemeente=bagh_gemeente,
        identificatie="03630000000001",
        volgnummer=1,
    )


@pytest.fixture()
def vestiging_schema_json() -> dict():
    path = HERE / "files/vestiging.json"
    return json.loads(path.read_text())


@pytest.fixture()
def vestiging_schema(vestiging_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(vestiging_schema_json)


@pytest.fixture()
def vestiging_adres_model(vestiging_models):
    return vestiging_models["adres"]


@pytest.fixture()
def vestiging_vestiging_model(vestiging_models):
    return vestiging_models["vestiging"]


@pytest.fixture()
def bezoek_adres1(vestiging_adres_model):
    return vestiging_adres_model.objects.create(
        id=1, plaats="Amsterdam", straat="Strawinskylaan", nummer=123, postcode="1234AB"
    )


@pytest.fixture()
def bezoek_adres2(vestiging_adres_model):
    return vestiging_adres_model.objects.create(
        id=2, plaats="Amsterdam", straat="Singel", nummer=321, postcode="1011ZZ"
    )


@pytest.fixture()
def post_adres1(vestiging_adres_model):
    return vestiging_adres_model.objects.create(
        id=3, plaats="Amsterdam", straat="Dam", nummer=1, postcode="1000AA"
    )


@pytest.fixture()
def vestiging1(vestiging_vestiging_model, bezoek_adres1, post_adres1):
    return vestiging_vestiging_model.objects.create(
        id=1, naam="Snake Oil", bezoek_adres=bezoek_adres1, post_adres=post_adres1
    )


@pytest.fixture()
def vestiging2(vestiging_vestiging_model, bezoek_adres2, post_adres1):
    return vestiging_vestiging_model.objects.create(
        id=2, naam="Haarlemmer olie", bezoek_adres=bezoek_adres2, post_adres=post_adres1
    )


@pytest.fixture()
def vestiging_dataset(vestiging_schema_json) -> Dataset:
    return Dataset.objects.create(name="vestiging", schema_data=vestiging_schema_json)


@pytest.fixture()
def vestiging_models(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["vestiging"]


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


# ---| >> START no display check>> FIETSPAALTJES  >>no display check >> |---#


@pytest.fixture()
def fietspaaltjes_schema(fietspaaltjes_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(fietspaaltjes_schema_json)


@pytest.fixture()
def fietspaaltjes_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["fietspaaltjes"]["fietspaaltjes"]


@pytest.fixture()
def fietspaaltjes_schema_json() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/fietspaaltjes.json"
    return json.loads(path.read_text())


@pytest.fixture()
def fietspaaltjes_dataset(fietspaaltjes_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="fietspaaltjes", schema_data=fietspaaltjes_schema_json
    )


@pytest.fixture()
def fietspaaltjes_data(fietspaaltjes_model):
    return fietspaaltjes_model.objects.create(
        id="Fietsplaatje record met display",
        geometry="POINT (123207.6558130105 486624.6399002579)",
        street="Weesperplein",
        at="Geschutswerf",
        area="Amsterdam-Centrum",
        score_2013=None,
        score_current="reference for DISPLAY FIELD",
        count=6,
        paaltjes_weg=["nu paaltje(s)"],
        soort_paaltje=["paaltje(s) ong. 75cm hoog", "verwijderde paaltjes"],
        uiterlijk=["rood/wit"],
        type=["vast", "uitneembaar"],
        ruimte=["Voldoende: 1.6m of meer"],
        markering=["markering ontbreekt", "onvoldoende markering"],
        beschadigingen=None,
        veiligheid=["overzichtelijke locatie"],
        zicht_in_donker=["onvoldoende reflectie op paal"],
        soort_weg=["rijbaan fiets+auto", "fietspad"],
        noodzaak=["nodig tegen sluipverkeer"],
    )


@pytest.fixture()
def fietspaaltjes_schema_no_display(
    fietspaaltjes_schema_json_no_display,
) -> DatasetSchema:
    return DatasetSchema.from_dict(fietspaaltjes_schema_json_no_display)


@pytest.fixture()
def fietspaaltjes_model_no_display(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["fietspaaltjesnodisplay"]["fietspaaltjesnodisplay"]


@pytest.fixture()
def fietspaaltjes_schema_json_no_display() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/fietspaaltjes_no_display.json"
    return json.loads(path.read_text())


@pytest.fixture()
def fietspaaltjes_dataset_no_display(fietspaaltjes_schema_json_no_display) -> Dataset:
    return Dataset.objects.create(
        name="fietspaaltjesnodisplay", schema_data=fietspaaltjes_schema_json_no_display
    )


@pytest.fixture()
def fietspaaltjes_data_no_display(fietspaaltjes_model_no_display):
    return fietspaaltjes_model_no_display.objects.create(
        id="Fietsplaatje record zonder display",
        geometry="POINT (123207.6558130105 486624.6399002579)",
        street="Weesperplein",
        at="Geschutswerf",
        area="Amsterdam-Centrum",
        score_2013=None,
        score_current="reference for DISPLAY FIELD",
        count=6,
        paaltjes_weg=["nu paaltje(s)"],
        soort_paaltje=["paaltje(s) ong. 75cm hoog", "verwijderde paaltjes"],
        uiterlijk=["rood/wit"],
        type=["vast", "uitneembaar"],
        ruimte=["Voldoende: 1.6m of meer"],
        markering=["markering ontbreekt", "onvoldoende markering"],
        beschadigingen=None,
        veiligheid=["overzichtelijke locatie"],
        zicht_in_donker=["onvoldoende reflectie op paal"],
        soort_weg=["rijbaan fiets+auto", "fietspad"],
        noodzaak=["nodig tegen sluipverkeer"],
    )


# --| >> EINDE no display check>> FIETSPAALTJES  >>no display check >> |--#

# --| >> START uri check>> EXPLOSIEVEN  >> uri check >> |--#


@pytest.fixture()
def explosieven_schema_json() -> dict:
    """ Fixture to return the schema json for """
    path = HERE / "files/explosieven.json"
    return json.loads(path.read_text())


@pytest.fixture()
def explosieven_schema(
    explosieven_schema_json,
) -> DatasetSchema:
    return DatasetSchema.from_dict(explosieven_schema_json)


@pytest.fixture()
def explosieven_dataset(explosieven_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="explosieven", schema_data=explosieven_schema_json
    )


@pytest.fixture()
def explosieven_model(filled_router):
    # Using filled_router so all urls can be generated too.
    return filled_router.all_models["explosieven"]["verdachtgebied"]


@pytest.fixture()
def explosieven_data(explosieven_model):
    return explosieven_model.objects.create(
        id=1,
        pdf="https://host.domain/file space space.extension",
        emailadres="account@host.domain",
    )


@pytest.fixture()
def indirect_self_ref_schema_json() -> dict():
    path = HERE / "files/indirect-self-ref.json"
    return json.loads(path.read_text())


@pytest.fixture()
def indirect_self_ref_schema(indirect_self_ref_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(indirect_self_ref_schema_json)


@pytest.fixture()
def indirect_self_ref_dataset(indirect_self_ref_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="indirect_self_ref", schema_data=indirect_self_ref_schema_json
    )


# --| >> EINDE uri check>> EXPLOSIEVEN  >> uri check >> |--#


@pytest.fixture()
def download_url_schema_json() -> dict():
    path = HERE / "files/download-url.json"
    return json.loads(path.read_text())


@pytest.fixture()
def download_url_schema(download_url_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(download_url_schema_json)


@pytest.fixture()
def download_url_dataset(download_url_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="download_url", schema_data=download_url_schema_json
    )


@pytest.fixture()
def meldingen_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/meldingen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def meldingen_schema(meldingen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(meldingen_schema_json)


@pytest.fixture()
def meldingen_dataset(meldingen_schema_json) -> Dataset:
    return Dataset.objects.create(name="meldingen", schema_data=meldingen_schema_json)


@pytest.fixture()
def gebieden_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/gebieden.json"
    return json.loads(path.read_text())


@pytest.fixture()
def gebieden_schema(gebieden_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(gebieden_schema_json)


@pytest.fixture()
def gebieden_dataset(gebieden_schema_json) -> Dataset:
    return Dataset.objects.create(name="gebieden", schema_data=gebieden_schema_json)


@pytest.fixture()
def woningbouwplannen_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/woningbouwplannen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def woningbouwplannen_schema(woningbouwplannen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(woningbouwplannen_schema_json)


@pytest.fixture()
def woningbouwplannen_dataset(woningbouwplannen_schema_json) -> Dataset:
    return Dataset.objects.create(
        name="woningbouwplannen", schema_data=woningbouwplannen_schema_json
    )


@pytest.fixture()
def statistieken_model(filled_router):
    return filled_router.all_models["meldingen"]["statistieken"]


@pytest.fixture()
def buurten_model(filled_router):
    return filled_router.all_models["gebieden"]["buurten"]


@pytest.fixture()
def wijken_model(filled_router):
    return filled_router.all_models["gebieden"]["wijken"]


@pytest.fixture()
def ggwgebieden_model(filled_router):
    return filled_router.all_models["gebieden"]["ggwgebieden"]


@pytest.fixture()
def woningbouwplan_model(filled_router):
    return filled_router.all_models["woningbouwplannen"]["woningbouwplan"]


@pytest.fixture()
def statistieken_data(statistieken_model):
    statistieken_model.objects.create(
        id=1,
        buurt="03630000000078",
    )


@pytest.fixture()
def buurten_data(buurten_model):
    buurten_model.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        ligt_in_wijk_id="03630012052035.1",
    )
    buurten_model.objects.create(
        id="03630000000078.2", identificatie="03630000000078", volgnummer=2
    )


@pytest.fixture()
def wijken_data(wijken_model):
    wijken_model.objects.create(
        id="03630012052035.1", identificatie="03630012052035", volgnummer=1
    )


@pytest.fixture()
def ggwgebieden_data(ggwgebieden_model):
    ggwgebieden_model.objects.create(
        id="03630950000000.1", identificatie="03630950000000", volgnummer=1
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        ggwgebieden_id="03630950000000.1", bestaat_uit_buurten_id="03630000000078.1"
    )


@pytest.fixture()
def woningbouwplannen_data(woningbouwplan_model):
    woningbouwplan_model.objects.create(id="1")
    woningbouwplan_model.buurten.through.objects.create(
        woningbouwplan_id="1", buurten_id="03630000000078"
    )
    # woningbouwplan_model.objects.create(id="2", testbuurt="03630000000078")
    # woningbouwplan_model.bestaat_uit_buurten.through.objects.create(
    #    woningbouwplan_id="2", bestaat_uit_buurten_id="03630000000078"
    # )


@pytest.fixture()
def parkeerwacht_profile() -> ProfileSchema:
    path = HERE / "files/profiles/parkeerwacht.json"
    schema = ProfileSchema.from_dict(json.loads(path.read_text()))
    return Profile.create_for_schema(schema)
