from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Type, cast

import pytest
from authorization_django import jwks
from django.contrib.auth.models import AnonymousUser
from django.contrib.gis.geos import GEOSGeometry, Point
from django.core.handlers.wsgi import WSGIRequest
from django.db import connection
from django.utils.functional import SimpleLazyObject
from django.utils.timezone import get_current_timezone
from jwcrypto.jwt import JWT
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from schematools.contrib.django.auth_backend import RequestProfile
from schematools.contrib.django.models import Dataset, DynamicModel, Profile
from schematools.types import DatasetSchema, ProfileSchema

from rest_framework_dso.crs import RD_NEW
from rest_framework_dso.renderers import HALJSONRenderer
from tests.test_rest_framework_dso.models import Actor, Category, Location, Movie, MovieUser

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

    request.user = AnonymousUser()
    request.auth_profile = RequestProfile(request)
    request.is_authorized_for = lambda *scopes: True

    # Temporal modifications. Usually done via TemporalTableMiddleware
    request.versioned = False
    return request


@pytest.fixture()
def drf_request(api_request) -> Request:
    """The wrapped WSGI Request as a Django-Rest-Framework request.
    This is the 'request' object that APIView.dispatch() creates.
    """
    request = Request(api_request)
    request.accepted_renderer = HALJSONRenderer()
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
        not router.registry or router.registry == router.static_routes
    ), "DynamicRouter already has URL patterns before test starts!"

    yield router

    # Only any changes that tests may have done to the router
    if router.is_initialized():
        router.clear_urls()


@pytest.fixture()
def filled_router(router, dynamic_models):
    """The fixture to add when dynamic viewsets are needed in the test.
    Without this fixture, the viewsets are not generated, and hence ``reverse()`` won't work.

    Note that ``pytest_runtest_call()`` performs post-fixture collection logic on this.
    """
    return router


class _LazyDynamicModels:
    """Create models on demand on retrieval."""

    def __init__(self, router):
        self.router = router
        self.datasets = None

    def _get_model(self, dataset_name, model_name):
        if not self.router.all_models:
            _initialize_router(self.router)

        try:
            app = self.router.all_models[dataset_name]
        except KeyError:
            loaded = sorted(self.router.all_models.keys())
            later = set(ds.schema.id for ds in Dataset.objects.db_enabled()).difference(loaded)
            if dataset_name in later:
                raise KeyError(
                    "New dataset fixtures were loaded after the router "
                    f"was initialized: {','.join(sorted(later))}"
                ) from None
            else:
                raise KeyError(
                    f"Dataset app '{dataset_name}' not found. Loaded are: {','.join(loaded)}"
                ) from None

        try:
            return app[model_name]
        except KeyError:
            raise KeyError(
                f"Model {model_name} does not exist in dataset '{dataset_name}'"
            ) from None

    def __getitem__(self, dataset_name) -> _LazyDynamicModels._LazyApp:
        return self._LazyApp(self, dataset_name)

    class _LazyApp:
        def __init__(self, parent: _LazyDynamicModels, dataset_name):
            self.parent = parent
            self.dataset_name = dataset_name

        def __getitem__(self, model_name) -> Type[DynamicModel]:
            # Delay model creation as much as possible. Only when the attributes are read,
            # the actual model is constructed. This avoids early router reloads.
            return cast(
                Type[DynamicModel],
                SimpleLazyObject(lambda: self.parent._get_model(self.dataset_name, model_name)),
            )


@pytest.fixture()
def dynamic_models(router):
    """Generated models from the router.
    Note that ``pytest_runtest_call()`` performs post-fixture collection logic on this.
    """
    # This uses a class to generate the models on demand.
    return _LazyDynamicModels(router)


def pytest_runtest_call(item):
    """Make sure tables of remaining dataset fixtures are also created."""
    if "dynamic_models" in item.fixturenames or "filled_router" in item.fixturenames:
        from dso_api.dynamic_api.urls import router

        if not router.is_initialized():
            # Perform late initialization if this didn't happen yet on demand.
            _initialize_router(router)
        else:
            # If router already initialized (e.g. via _LazyDynamicModels), test whether no
            # datasets were created afterwards. That likely means the fixture order isn't correct.
            datasets = {ds.schema.id for ds in Dataset.objects.db_enabled()}
            if len(datasets) > len(router.all_models):
                added = datasets - set(router.all_models.keys())
                raise RuntimeError(
                    f"More dataset fixtures were defined after 'filled_router':"
                    f" {','.join(sorted(added))}"
                )


def _initialize_router(router):
    # Model creation on demand, always create viewsets too.
    # It's very hard to reliably determine whether these are needed or not.
    # Optimizing this would risk breaking various reverse() calls in tests.
    router.reload()
    if not router.is_initialized():
        raise RuntimeError(
            "The 'filled_router' or 'dynamic_models' fixture was requested, "
            "but no dataset fixtures were defined for this test."
        )

    _create_tables_if_missing(router.all_models)


def _create_tables_if_missing(dynamic_models):
    """Create the database tables for dynamic models"""
    table_names = connection.introspection.table_names()

    with connection.schema_editor() as schema_editor:
        for dataset_id, models in dynamic_models.items():
            for model in models.values():
                if model._meta.db_table not in table_names:
                    schema_editor.create_model(model)


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
def afval_cluster_model(afval_dataset, dynamic_models):
    return dynamic_models["afvalwegingen"]["clusters"]


@pytest.fixture()
def afval_cluster(afval_cluster_model):
    return afval_cluster_model.objects.create(id="c1", status="valid")


@pytest.fixture()
def afval_container_model(afval_dataset, dynamic_models):
    return dynamic_models["afvalwegingen"]["containers"]


@pytest.fixture()
def afval_adresloopafstand_model(afval_dataset, dynamic_models):
    return dynamic_models["afvalwegingen"]["adres_loopafstand"]


@pytest.fixture()
def afval_container(afval_container_model, afval_cluster):
    return afval_container_model.objects.create(
        id=1,
        serienummer="foobar-123",
        eigenaar_naam="Dataservices",
        # set to fixed dates to the CSV export can also check for desired formatting
        datum_creatie=date(2021, 1, 3),
        datum_leegmaken=get_current_timezone().localize(datetime(2021, 1, 3, 12, 13, 14)),
        cluster=afval_cluster,
        geometry=Point(10, 10),  # no SRID on purpose, should use django model field.
    )


@pytest.fixture()
def afval_adresloopafstand(afval_adresloopafstand_model):
    return afval_adresloopafstand_model.objects.create(
        id=999,
        serienummer="foobar-456",
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
def bommen_dataset(bommen_schema) -> Dataset:
    return Dataset.create_for_schema(schema=bommen_schema)


@pytest.fixture()
def bommen_v2_schema_json() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/bommen@2.0.0.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bommen_v2_schema(bommen_v2_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(bommen_v2_schema_json)


@pytest.fixture()
def bommen_v2_dataset(bommen_v2_schema) -> Dataset:
    return Dataset.create_for_schema(schema=bommen_v2_schema)


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
    return "http://remote-server/unittest/brp/{table_id}"


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


@pytest.fixture()
def hcbrk_dataset() -> Dataset:
    return Dataset.objects.create(
        name="hcbrk",
        schema_data=json.loads((HERE / "files" / "hcbrk.json").read_text()),
        enable_db=False,
        # URL netloc needs ".acceptatie." because of HTTP pool selection.
        endpoint_url="http://fake.acceptatie.kadaster/esd/bevragen/v1/{table_id}",
        url_prefix="remote",
    )


# Dataset with auth scopes on fields.


@pytest.fixture()
def geometry_auth_schema_json() -> dict:
    return json.loads((HERE / "files" / "geometry_auth.json").read_text())


@pytest.fixture()
def geometry_auth_schema(geometry_auth_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(geometry_auth_schema_json)


@pytest.fixture()
def geometry_auth_dataset(geometry_auth_schema):
    return Dataset.create_for_schema(schema=geometry_auth_schema)


@pytest.fixture()
def geometry_auth_model(geometry_auth_dataset, dynamic_models):
    return dynamic_models["geometry_auth"]["things"]


@pytest.fixture()
def geometry_auth_thing(geometry_auth_model):
    return geometry_auth_model.objects.create(
        id=1,
        metadata="secret",
        geometry=Point(10, 10),
    )


# Dataset with auth scopes on the entire dataset.


@pytest.fixture()
def geometry_authdataset_schema_json() -> dict:
    return json.loads((HERE / "files" / "geometry_authdataset.json").read_text())


@pytest.fixture()
def geometry_authdataset_schema(geometry_authdataset_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(geometry_authdataset_schema_json)


@pytest.fixture()
def geometry_authdataset_dataset(geometry_authdataset_schema):
    return Dataset.create_for_schema(schema=geometry_authdataset_schema)


@pytest.fixture()
def geometry_authdataset_model(geometry_authdataset_dataset, dynamic_models):
    return dynamic_models["geometry_authdataset"]["things"]


@pytest.fixture()
def geometry_authdataset_thing(geometry_authdataset_model):
    return geometry_authdataset_model.objects.create(
        id=1,
        metadata="secret",
        geometry=Point(10, 10),
    )


@pytest.fixture
def category() -> Category:
    """A dummy model to test our API with"""
    return Category.objects.create(
        pk=1, name="bar", last_updated_by=MovieUser.objects.create(name="bar_man")
    )


@pytest.fixture
def movie(category) -> Movie:
    """A dummy model to test our API with"""
    result = Movie.objects.create(name="foo123", category=category)
    result.actors.set(
        [
            Actor.objects.create(name="John Doe"),
            Actor.objects.create(
                name="Jane Doe", last_updated_by=MovieUser.objects.create(name="jane_updater")
            ),
        ]
    )
    return result


@pytest.fixture
def location() -> Location:
    """A dummy model to test our API with"""
    return Location.objects.create(geometry=GEOSGeometry("Point(10 10)", srid=RD_NEW))


@pytest.fixture()
def parkeervakken_schema_json() -> dict:
    path = HERE / "files/parkeervakken.json"
    return json.loads(path.read_text())


@pytest.fixture()
def parkeervakken_schema(parkeervakken_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(parkeervakken_schema_json)


@pytest.fixture()
def parkeervakken_dataset(parkeervakken_schema_json) -> Dataset:
    return Dataset.objects.create(name="parkeervakken", schema_data=parkeervakken_schema_json)


@pytest.fixture()
def parkeervakken_parkeervak_model(parkeervakken_dataset, dynamic_models):
    return dynamic_models["parkeervakken"]["parkeervakken"]


@pytest.fixture()
def parkeervakken_regime_model(parkeervakken_dataset, dynamic_models):
    return dynamic_models["parkeervakken"]["parkeervakken_regimes"]


@pytest.fixture()
def vestiging_schema_json() -> dict:
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
def vestiging_models(vestiging_dataset, dynamic_models):
    return dynamic_models["vestiging"]


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
def fietspaaltjes_model(fietspaaltjes_dataset, dynamic_models):
    return dynamic_models["fietspaaltjes"]["fietspaaltjes"]


@pytest.fixture()
def fietspaaltjes_schema_json() -> dict:
    """Fixture to return the schema json for """
    path = HERE / "files/fietspaaltjes.json"
    return json.loads(path.read_text())


@pytest.fixture()
def fietspaaltjes_dataset(fietspaaltjes_schema_json) -> Dataset:
    return Dataset.objects.create(name="fietspaaltjes", schema_data=fietspaaltjes_schema_json)


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
def fietspaaltjes_model_no_display(fietspaaltjes_dataset_no_display, dynamic_models):
    return dynamic_models["fietspaaltjesnodisplay"]["fietspaaltjesnodisplay"]


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
    return Dataset.objects.create(name="explosieven", schema_data=explosieven_schema_json)


@pytest.fixture()
def explosieven_model(explosieven_dataset, dynamic_models):
    return dynamic_models["explosieven"]["verdachtgebied"]


@pytest.fixture()
def explosieven_data(explosieven_model):
    return explosieven_model.objects.create(
        id=1,
        pdf="https://host.domain/file space space.extension",
        emailadres="account@host.domain",
    )


@pytest.fixture()
def indirect_self_ref_schema_json() -> dict:
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


@pytest.fixture()
def ligplaatsen_model(indirect_self_ref_dataset, dynamic_models):
    return dynamic_models["selfref"]["ligplaatsen"]


# --| >> EINDE uri check>> EXPLOSIEVEN  >> uri check >> |--#


@pytest.fixture()
def download_url_schema_json() -> dict:
    path = HERE / "files/download-url.json"
    return json.loads(path.read_text())


@pytest.fixture()
def download_url_schema(download_url_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(download_url_schema_json)


@pytest.fixture()
def download_url_dataset(download_url_schema_json) -> Dataset:
    return Dataset.objects.create(name="download", schema_data=download_url_schema_json)


@pytest.fixture()
def meldingen_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/meldingen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def meldingen_schema(meldingen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(meldingen_schema_json)


@pytest.fixture()
def meldingen_dataset(
    gebieden_dataset,  # dependency in schema
    meldingen_schema_json,
) -> Dataset:
    return Dataset.objects.create(name="meldingen", schema_data=meldingen_schema_json)


@pytest.fixture()
def gebieden_models(
    gebieden_dataset,
    dynamic_models,
):
    return dynamic_models["gebieden"]


@pytest.fixture()
def gebieden_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/gebieden.json"
    return json.loads(path.read_text())


@pytest.fixture()
def gebieden_schema(gebieden_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(gebieden_schema_json)


@pytest.fixture()
def _gebieden_dataset(gebieden_schema_json) -> Dataset:
    """Internal"""
    return Dataset.objects.create(name="gebieden", schema_data=gebieden_schema_json)


@pytest.fixture()
def gebieden_dataset(_gebieden_dataset, woningbouwplannen_dataset) -> Dataset:
    """Make sure gebieden + woningbouwplannen is always combined,
    because woningbouwplannen has a reverse dependency on 'gebieden'.
    This avoids accidentally leaving out the reverse dependency.
    """
    return _gebieden_dataset


@pytest.fixture()
def bag_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/bag.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bag_schema(bag_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(bag_schema_json)


@pytest.fixture()
def bag_dataset(bag_schema_json) -> Dataset:
    return Dataset.objects.create(name="bag", schema_data=bag_schema_json)


@pytest.fixture()
def woningbouwplannen_schema_json() -> dict:
    """ Fixture to return the schema json """
    path = HERE / "files/woningbouwplannen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def woningbouwplannen_schema(woningbouwplannen_schema_json) -> DatasetSchema:
    return DatasetSchema.from_dict(woningbouwplannen_schema_json)


@pytest.fixture()
def woningbouwplannen_dataset(woningbouwplannen_schema_json, _gebieden_dataset) -> Dataset:
    # Woningbouwplannen has a dependency on gebieden,
    # so this fixture makes sure it's always loaded.
    return Dataset.objects.create(
        name="woningbouwplannen", schema_data=woningbouwplannen_schema_json
    )


@pytest.fixture()
def statistieken_model(meldingen_dataset, gebieden_dataset, dynamic_models):
    return dynamic_models["meldingen"]["statistieken"]


@pytest.fixture()
def panden_model(bag_dataset, dynamic_models):
    return dynamic_models["bag"]["panden"]


@pytest.fixture()
def dossiers_model(bag_dataset, dynamic_models):
    return dynamic_models["bag"]["dossiers"]


@pytest.fixture()
def buurten_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["buurten"]


@pytest.fixture()
def wijken_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["wijken"]


@pytest.fixture()
def ggwgebieden_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["ggwgebieden"]


@pytest.fixture()
def woningbouwplan_model(woningbouwplannen_dataset, dynamic_models):
    return dynamic_models["woningbouwplannen"]["woningbouwplan"]


@pytest.fixture()
def statistieken_data(statistieken_model, buurten_data):
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
def panden_data(panden_model, dossiers_model):
    panden_model.objects.create(
        id="0363100012061164.3",
        volgnummer=3,
        identificatie="0363100012061164",
        naam="Voorbeeldpand",
        heeft_dossier_id="GV00000406",
    )
    dossiers_model.objects.create(dossier="GV00000406")


@pytest.fixture()
def wijken_data(wijken_model):
    wijken_model.objects.create(
        id="03630012052035.1", identificatie="03630012052035", volgnummer=1
    )


@pytest.fixture()
def ggwgebieden_data(ggwgebieden_model, buurten_data):
    ggwgebieden_model.objects.create(
        id="03630950000000.1", identificatie="03630950000000", volgnummer=1
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        ggwgebieden_id="03630950000000.1", bestaat_uit_buurten_id="03630000000078.1"
    )


@pytest.fixture()
def woningbouwplannen_data(woningbouwplan_model, buurten_data):
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
