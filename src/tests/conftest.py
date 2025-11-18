from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pytest
from authorization_django import jwks
from django.contrib.gis.geos import GEOSGeometry, Point
from django.core.handlers.wsgi import WSGIRequest
from django.db import connection
from django.utils.functional import SimpleLazyObject
from django.utils.timezone import get_current_timezone
from jwcrypto.jwt import JWT
from psycopg.sql import SQL, Identifier
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from schematools.contrib.django.models import Dataset, DynamicModel, Profile
from schematools.loaders import FileSystemProfileLoader, FileSystemSchemaLoader
from schematools.types import DatasetSchema, Scope

from dso_api.dynamic_api.constants import DEFAULT
from tests.test_rest_framework_dso.models import Actor, Category, Location, Movie, MovieUser
from tests.utils import api_request_with_scopes, to_drf_request

HERE = Path(__file__).parent
DATE_2021_FEB = datetime(2021, 2, 28, 10, 0, tzinfo=get_current_timezone())
DATE_2021_JUNE = datetime(2021, 6, 11, 10, 0, tzinfo=get_current_timezone())

# Database formats
DAM_SQUARE_LATLON = "SRID=4326;POINT (4.8936582 52.3731716)"  # x,y ordering in database
DAM_SQUARE_RD = "SRID=28992;POINT (121389 487369)"

# Django formats
DAM_SQUARE_POINT_NO_SRID = Point(121389, 487369)  # uses django model field srid.
DAM_SQUARE_POINT = Point(121389, 487369, srid=28992)

# Allow comparing on systems that have different gdal/proj4 versions
DAM_SQUARE_LATLON_APPROX = pytest.approx([4.8936582, 52.3731716], rel=1e-6)  # x,y ordering
DAM_SQUARE_WGS84_APPROX = pytest.approx([52.3731716, 4.8936582], rel=1e-6)  # north,east (y,x)
DAM_SQUARE_RD_APPROX = pytest.approx([121389, 487369], rel=0.001)


# In test files we use a lot of non-existent scopes, so instead of writing scope
# json files we monkeypatch this method.
@pytest.fixture(autouse=True)
def patch_find_scope_by_id(monkeypatch):
    monkeypatch.setattr(DatasetSchema, "_find_scope_by_id", Scope.from_string)


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """Request factory for APIView classes"""
    return APIRequestFactory()


@pytest.fixture()
def api_request() -> WSGIRequest:
    """Return a very basic Request object. This can be used for the APIClient.
    The DRF views use a different request object internally, see `drf_request` for that.
    """
    return api_request_with_scopes([])


@pytest.fixture()
def drf_request(api_request) -> Request:
    """The wrapped WSGI Request as a Django-Rest-Framework request.
    This is the 'request' object that APIView.dispatch() creates.
    """
    return to_drf_request(api_request)


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
            app = self.router.all_models[dataset_name][DEFAULT]
        except KeyError:
            loaded = sorted(self.router.all_models.keys())
            later = {ds.schema.id for ds in Dataset.objects.db_enabled()}.difference(loaded)
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
            available = ",".join(sorted(app.keys()))
            raise KeyError(
                f"Model {model_name} does not exist in dataset '{dataset_name}'. "  # noqa: E713
                f"Available are: {available}"
            ) from None

    def __getitem__(self, dataset_name) -> _LazyDynamicModels._LazyApp:
        return self._LazyApp(self, dataset_name)

    class _LazyApp:
        def __init__(self, parent: _LazyDynamicModels, dataset_name):
            self.parent = parent
            self.dataset_name = dataset_name

        def __getitem__(self, model_name) -> type[DynamicModel]:
            # Delay model creation as much as possible. Only when the attributes are read,
            # the actual model is constructed. This avoids early router reloads.
            return cast(
                type[DynamicModel],
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
        for _dataset_id, versions in dynamic_models.items():
            for model in versions[DEFAULT].values():
                if model._meta.db_table not in table_names:
                    schema_editor.create_model(model)


@pytest.fixture
def activate_dbroles(settings, movies_dataset, movies_data, directors_data):
    """Fixture for testing enduser context against movies data.
    This mimicks the setup in aaddbroles pipeline in the dp-infra repo

    It creates the following structure:

        scope_test_director                       scope_test_openbaar
            |    _________________________________|
            |   |                   |             |
        test_user_email_role  anonymous_role  internal_role
                |_________________|_______________|
                                  |
                            test_noinherit_role (noinherit)
                                  |
                                db_user (inherit)

    With the following scope privileges:

        movies_movie SELECT -> scope_test_openbaar
        movies_category SELECT -> scope_test_openbaar
        movies_director SELECT -> scope_test_director
    """
    test_user_role = Identifier(f"{settings.TEST_USER_EMAIL}_role")
    test_user_role_filtered = Identifier(f"{settings.TEST_USER_EMAIL}_role.filtered")

    with connection.cursor() as curs:
        curs.execute(
            SQL(
                """
                    CREATE ROLE {0};
                    CREATE ROLE {1};
                    CREATE ROLE {2};
                    CREATE ROLE {3};
                    CREATE ROLE {4} NOINHERIT;
                    GRANT {0},{1},{2},{3} TO {4};
                    GRANT {4} TO {5};
                """
            ).format(
                Identifier(settings.INTERNAL_ROLE),
                Identifier(settings.ANONYMOUS_ROLE),
                test_user_role,
                test_user_role_filtered,
                Identifier(settings.TEST_NOINHERIT_ROLE),
                Identifier(settings.DB_USER),
            )
        )

        # Create scopes
        movies_table = movies_dataset.tables.get(name="movie").db_table
        category_table = movies_dataset.tables.get(name="category").db_table
        actor_table = movies_dataset.tables.get(name="actor").db_table
        director_table = movies_dataset.tables.get(name="director").db_table
        actors_through_table = movies_dataset.schema.through_tables[0].db_name
        curs.execute(
            SQL(
                """
                CREATE ROLE scope_test_openbaar;
                CREATE ROLE scope_test_director;
                GRANT scope_test_openbaar to {0},{1},{2},{3};
                GRANT scope_test_director to {2},{3};
            """
            ).format(
                Identifier(settings.ANONYMOUS_ROLE),
                Identifier(settings.INTERNAL_ROLE),
                test_user_role,
                test_user_role_filtered,
            )
        )

    # We execute the grants of table permissions in the default connection,
    # because the tables are only visible inside the test session transaction.
    with connection.cursor() as c:
        c.execute(
            SQL(
                """
                GRANT SELECT ON {0},{1},{2},{3} TO scope_test_openbaar;
                GRANT SELECT ON {4} TO scope_test_director;
            """
            ).format(
                Identifier(movies_table),
                Identifier(category_table),
                Identifier(actor_table),
                Identifier(actors_through_table),
                Identifier(director_table),
            )
        )

    settings.DATABASE_SET_ROLE = True

    yield

    settings.DATABASE_SET_ROLE = False

    with connection.cursor() as curs:
        curs.execute(
            SQL(
                """
                DROP OWNED BY scope_test_openbaar,scope_test_director;
                DROP ROLE IF EXISTS {0},{1},{2},{3},{4};
                DROP ROLE IF EXISTS scope_test_openbaar,scope_test_director;
            """
            ).format(
                Identifier(settings.INTERNAL_ROLE),
                Identifier(settings.ANONYMOUS_ROLE),
                Identifier(settings.TEST_NOINHERIT_ROLE),
                test_user_role,
                test_user_role_filtered,
            )
        )


@pytest.fixture()
def schema_loader() -> FileSystemSchemaLoader:
    """A shared cache between all datasets that are constructed by the tests."""
    return FileSystemSchemaLoader(HERE / "files/datasets")


@pytest.fixture
def aardgasverbruik_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("aardgasverbruik.json")


@pytest.fixture
def aardgasverbruik_dataset(aardgasverbruik_schema) -> Dataset:
    return Dataset.create_for_schema(aardgasverbruik_schema)


@pytest.fixture()
def afval_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("afval.json")


@pytest.fixture()
def afval_schema_rla(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("afval_rla.json")


@pytest.fixture()
def afval_dataset(afval_schema) -> Dataset:
    return Dataset.create_for_schema(afval_schema)


@pytest.fixture()
def afval_dataset_rla(afval_schema_rla) -> Dataset:
    return Dataset.create_for_schema(afval_schema_rla)


@pytest.fixture()
def disabled_afval_dataset(afval_dataset) -> Dataset:
    afval_dataset.enable_api = False
    afval_dataset.save(update_fields=["enable_api"])
    return afval_dataset


@pytest.fixture()
def afval_dataset_subpath(afval_schema) -> Dataset:
    return Dataset.create_for_schema(afval_schema, path="sub/path/afvalwegingen")


@pytest.fixture()
def afval_cluster_model(afval_dataset, dynamic_models):
    return dynamic_models["afvalwegingen"]["clusters"]


@pytest.fixture()
def afval_cluster_model_rla(afval_dataset_rla, dynamic_models):
    return dynamic_models["afvalwegingen_rla"]["clusters"]


@pytest.fixture()
def afval_cluster(afval_cluster_model):
    return afval_cluster_model.objects.create(id="c1", status="valid")


@pytest.fixture()
def afval_cluster_rla(afval_cluster_model_rla):
    return afval_cluster_model_rla.objects.create(
        id="c2", status="valid", hide_confidential_info=True, geheim_veld="GEHEIM"
    )


@pytest.fixture()
def afval_container_model(afval_dataset, dynamic_models):
    return dynamic_models["afvalwegingen"]["containers"]


@pytest.fixture()
def afval_container_model_rla(afval_dataset_rla, dynamic_models):
    return dynamic_models["afvalwegingen_rla"]["containers"]


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
        datum_leegmaken=datetime(2021, 1, 3, 12, 13, 14, tzinfo=get_current_timezone()),
        cluster=afval_cluster,
        geometry=DAM_SQUARE_POINT_NO_SRID,
    )


@pytest.fixture()
def afval_container_rla(afval_container_model_rla, afval_cluster_rla):
    return afval_container_model_rla.objects.create(
        id=2,
        serienummer="foobar-234",
        eigenaar_naam="Dataservices",
        # set to fixed dates to the CSV export can also check for desired formatting
        datum_creatie=date(2021, 1, 3),
        datum_leegmaken=datetime(2021, 1, 3, 12, 13, 14, tzinfo=get_current_timezone()),
        cluster=afval_cluster_rla,
        geometry=DAM_SQUARE_POINT_NO_SRID,
        hide_confidential_info=True,
        eigenaar_details_telefoonnummer="02067777777",
        eigenaar_details_bsn="123456789",
    )


@pytest.fixture()
def afval_adresloopafstand(afval_adresloopafstand_model):
    return afval_adresloopafstand_model.objects.create(
        id=999,
        serienummer="foobar-456",
    )


@pytest.fixture()
def array_auth(schema_loader):
    schema = schema_loader.get_dataset_from_file("array_auth.json")
    return Dataset.create_for_schema(schema=schema)


@pytest.fixture()
def beheerkaar_basis_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("beheerkaart/basis/dataset.json")


@pytest.fixture()
def beheerkaart_basis_dataset(schema_loader, beheerkaar_basis_schema) -> Dataset:
    # path is needed to create a nested route, use same logic as `import schemas`.
    path = schema_loader._get_dataset_path(beheerkaar_basis_schema.id)
    return Dataset.create_for_schema(beheerkaar_basis_schema, path)


@pytest.fixture()
def bommen_schema_json() -> dict:
    """Fixture to return the schema json for"""
    path = HERE / "files/datasets/bommen.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bommen_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("bommen.json")


@pytest.fixture()
def bommen_dataset(bommen_schema) -> Dataset:
    return Dataset.create_for_schema(schema=bommen_schema)


@pytest.fixture()
def bommen_v2_schema_json() -> dict:
    """Fixture to return the schema json for"""
    path = HERE / "files/datasets/bommen@2.0.0.json"
    return json.loads(path.read_text())


@pytest.fixture()
def bommen_v2_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("bommen@2.0.0.json")


@pytest.fixture()
def bommen_v2_dataset(bommen_v2_schema) -> Dataset:
    return Dataset.create_for_schema(schema=bommen_v2_schema)


@pytest.fixture()
def hoofdroutes_schema(schema_loader):
    return schema_loader.get_dataset_from_file(HERE / "files/datasets/hoofdroutes.json")


@pytest.fixture()
def hoofdroutes_dataset(hoofdroutes_schema):
    return Dataset.create_for_schema(hoofdroutes_schema)


# Dataset with auth scopes on fields.


@pytest.fixture()
def geometry_auth_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("geometry_auth.json")


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
        geometry_with_auth=DAM_SQUARE_POINT_NO_SRID,
    )


# Dataset with auth scopes on the entire dataset.


@pytest.fixture()
def geometry_authdataset_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("geometry_authdataset.json")


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
        geometry=DAM_SQUARE_POINT_NO_SRID,
    )


# Dataset with multiple geometries.


@pytest.fixture()
def geometry_multiple_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("geometry_multiple.json")


@pytest.fixture()
def geometry_multiple_dataset(geometry_multiple_schema):
    return Dataset.create_for_schema(schema=geometry_multiple_schema)


@pytest.fixture()
def geometry_multiple_model(geometry_multiple_dataset, dynamic_models):
    return dynamic_models["geometry_multiple"]["things"]


@pytest.fixture()
def geometry_multiple_thing(geometry_multiple_model):
    return geometry_multiple_model.objects.create(
        id=1,
        metadata="secret",
        geometrie=DAM_SQUARE_POINT_NO_SRID,
        main_geometrie=DAM_SQUARE_POINT_NO_SRID,
    )


@pytest.fixture
def category() -> Category:
    """A dummy model to test our API with"""
    return Category.objects.create(
        id=1, name="bar", last_updated_by=MovieUser.objects.create(name="bar_man")
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


@pytest.fixture()
def movies_dataset(schema_loader) -> Dataset:
    schema = schema_loader.get_dataset_from_file("movies.json")
    return Dataset.create_for_schema(schema)


@pytest.fixture
def movies_category(movies_dataset, dynamic_models):
    bar_man = dynamic_models["movies"]["user"].objects.create(id=1, name="bar_man")
    return dynamic_models["movies"]["category"].objects.create(
        id=1, name="bar", last_updated_by=bar_man
    )


@pytest.fixture
def movies_model(movies_dataset, dynamic_models):
    return dynamic_models["movies"]["movie"]


@pytest.fixture
def movies_data(movies_model, movies_category):
    return [
        movies_model.objects.create(
            id=3,
            name="foo123",
            category=movies_category,
            date_added=datetime(2020, 1, 1, 0, 45, tzinfo=get_current_timezone()),
        ),
        movies_model.objects.create(
            id=4,
            name="test",
            category=movies_category,
            date_added=datetime(2020, 2, 2, 13, 15, tzinfo=get_current_timezone()),
        ),
    ]


@pytest.fixture()
def directors_model(movies_dataset, dynamic_models):
    return dynamic_models["movies"]["director"]


@pytest.fixture
def directors_data(directors_model):
    return [
        directors_model.objects.create(
            id=66,
            name="Sjaak Fellini",
        ),
    ]


@pytest.fixture
def movies_data_with_actors(movies_data, dynamic_models):
    """Extended fixture to test M2M"""
    Actor = dynamic_models["movies"]["actor"]
    MovieUser = dynamic_models["movies"]["user"]
    movies_data[0].actors.set(
        [
            Actor.objects.create(id=1, name="John Doe"),
            Actor.objects.create(
                id=2,
                name="Jane Doe",
                last_updated_by=MovieUser.objects.create(id=2, name="jane_updater"),
            ),
        ]
    )
    return movies_data


@pytest.fixture
def location() -> Location:
    """A dummy model to test our API with"""
    return Location.objects.create(geometry=GEOSGeometry("SRID=28992;Point (121400 487400)"))


@pytest.fixture()
def parkeervakken_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("parkeervakken.json")


@pytest.fixture()
def parkeervakken_dataset(parkeervakken_schema) -> Dataset:
    return Dataset.create_for_schema(parkeervakken_schema)


@pytest.fixture()
def parkeervakken_parkeervak_model(parkeervakken_dataset, dynamic_models):
    return dynamic_models["parkeervakken"]["parkeervakken"]


@pytest.fixture()
def parkeervakken_regime_model(parkeervakken_dataset, dynamic_models):
    return dynamic_models["parkeervakken"]["parkeervakken_regimes"]


@pytest.fixture()
def parkeervak(parkeervakken_parkeervak_model, parkeervakken_regime_model) -> DynamicModel:
    parkeervak = parkeervakken_parkeervak_model.objects.create(
        id="121138489666",
        type="File",
        soort="MULDER",
        aantal=1.0,
        e_type="",
        buurtcode="A05d",
        straatnaam="Zoutkeetsgracht",
    )
    parkeervakken_regime_model.objects.create(
        id=1,
        parent=parkeervak,
        bord="Laden en Lossen",
        dagen=["ma", "di", "wo", "do", "vr"],
        soort="MULDER",
        aantal=None,
        e_type="E7",
        kenteken="",
        opmerking="",
        begintijd="06:00:00",
        eindtijd="15:00:00",
        einddatum=None,
        begindatum=None,
    )
    parkeervakken_regime_model.objects.create(
        id=2,
        parent=parkeervak,
        bord="",
        dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
        soort="FISCAAL",
        aantal=None,
        e_type="",
        kenteken="",
        opmerking="",
        begintijd="00:00:00",
        eindtijd="23:59:00",
        einddatum=None,
        begindatum=None,
    )
    return parkeervak


@pytest.fixture()
def vestiging_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("vestiging.json")


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
def vestiging_dataset(vestiging_schema) -> Dataset:
    return Dataset.create_for_schema(vestiging_schema)


@pytest.fixture()
def vestiging_models(vestiging_dataset, dynamic_models):
    return dynamic_models["vestiging"]


@pytest.fixture
def fetch_tokendata(settings):
    """Fixture to create valid token data, scopes is flexible"""

    def _fetcher(scopes, subject):
        now = int(time.time())
        return {"iat": now, "exp": now + 30, "scopes": scopes, "sub": subject}

    return _fetcher


@pytest.fixture
def fetch_auth_token(fetch_tokendata, settings):
    """Fixture to create an auth token, scopes is flexible"""

    def _fetcher(scopes, subject=settings.TEST_USER_EMAIL):
        kid = "2aedafba-8170-4064-b704-ce92b7c89cc6"
        key = jwks.get_keyset().get_key(kid)
        token = JWT(header={"alg": "ES256", "kid": kid}, claims=fetch_tokendata(scopes, subject))
        token.make_signed_token(key)
        return token.serialize()

    return _fetcher


# ---| >> START no display check>> FIETSPAALTJES  >>no display check >> |---#


@pytest.fixture()
def fietspaaltjes_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("fietspaaltjes.json")


@pytest.fixture()
def fietspaaltjes_model(fietspaaltjes_dataset, dynamic_models):
    return dynamic_models["fietspaaltjes"]["fietspaaltjes"]


@pytest.fixture()
def fietspaaltjes_dataset(fietspaaltjes_schema) -> Dataset:
    return Dataset.create_for_schema(fietspaaltjes_schema)


@pytest.fixture()
def fietspaaltjes_dataset_subpath(fietspaaltjes_schema) -> Dataset:
    return Dataset.create_for_schema(fietspaaltjes_schema, path="sub/fietspaaltjes")


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
def fietspaaltjes_schema_no_display(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("fietspaaltjes_no_display.json")


@pytest.fixture()
def fietspaaltjes_model_no_display(fietspaaltjes_dataset_no_display, dynamic_models):
    return dynamic_models["fietspaaltjesnodisplay"]["fietspaaltjesnodisplay"]


@pytest.fixture()
def fietspaaltjes_dataset_no_display(fietspaaltjes_schema_no_display) -> Dataset:
    return Dataset.create_for_schema(fietspaaltjes_schema_no_display)


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


# start niet beschikbaar
@pytest.fixture()
def fietspaaltjes_schema_niet_beschikbaar(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("fietspaaltjes_niet_beschikbaar.json")


@pytest.fixture()
def fietspaaltjes_model_niet_beschikbaar(fietspaaltjes_dataset_niet_beschikbaar, dynamic_models):
    return dynamic_models["fietspaaltjesnietbeschikbaar"]["fietspaaltjesnietbeschikbaar"]


@pytest.fixture()
def fietspaaltjes_dataset_niet_beschikbaar(fietspaaltjes_schema_niet_beschikbaar) -> Dataset:
    return Dataset.create_for_schema(fietspaaltjes_schema_niet_beschikbaar)


@pytest.fixture()
def fietspaaltjes_dataset_subpath_niet_beschikbaar(
    fietspaaltjes_schema_niet_beschikbaar,
) -> Dataset:
    return Dataset.create_for_schema(
        fietspaaltjes_schema_niet_beschikbaar, path="sub/fietspaaltjes"
    )


@pytest.fixture()
def fietspaaltjes_data_niet_beschikbaar(fietspaaltjes_model_niet_beschikbaar):
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


# --| >> EINDE no display check>> FIETSPAALTJES  >>no display check >> |--#

# --| >> START uri check>> EXPLOSIEVEN  >> uri check >> |--#


@pytest.fixture()
def explosieven_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("explosieven.json")


@pytest.fixture()
def explosieven_dataset(explosieven_schema) -> Dataset:
    return Dataset.create_for_schema(explosieven_schema)


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
def huishoudelijkafval_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset("huishoudelijkafval")


@pytest.fixture()
def huishoudelijkafval_dataset(bag_dataset, huishoudelijkafval_schema, dynamic_models):
    return Dataset.create_for_schema(huishoudelijkafval_schema)


@pytest.fixture()
def huishoudelijkafval_data(dynamic_models, huishoudelijkafval_dataset):
    model = dynamic_models["huishoudelijkafval"]["cluster"]
    return model.objects.create(
        id=1,
    )


@pytest.fixture()
def indirect_self_ref_schema_json() -> dict:
    path = HERE / "files/datasets/indirect-self-ref.json"
    return json.loads(path.read_text())


@pytest.fixture()
def indirect_self_ref_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("indirect-self-ref.json")


@pytest.fixture()
def indirect_self_ref_dataset(indirect_self_ref_schema) -> Dataset:
    return Dataset.create_for_schema(indirect_self_ref_schema)


@pytest.fixture()
def ligplaatsen_model(indirect_self_ref_dataset, dynamic_models):
    return dynamic_models["selfref"]["ligplaatsen"]


# --| >> EINDE uri check>> EXPLOSIEVEN  >> uri check >> |--#


@pytest.fixture()
def meldingen_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("meldingen.json")


@pytest.fixture()
def meldingen_dataset(gebieden_dataset, meldingen_schema) -> Dataset:
    return Dataset.create_for_schema(meldingen_schema)


@pytest.fixture()
def gebieden_models(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]


@pytest.fixture()
def gebieden_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("gebieden.json")


@pytest.fixture()
def _gebieden_dataset(gebieden_schema) -> Dataset:
    """Internal"""
    return Dataset.create_for_schema(gebieden_schema)


@pytest.fixture()
def unconventional_temporal_dataset(schema_loader) -> dict:
    return Dataset.create_for_schema(
        schema_loader.get_dataset_from_file("unconventional_temporal.json")
    )


@pytest.fixture()
def unconventional_temporal_model(unconventional_temporal_dataset, dynamic_models) -> dict:
    return dynamic_models["unconventionaltemporal"]["unconventionaltemporaltable"]


@pytest.fixture()
def gebieden_dataset(_gebieden_dataset, woningbouwplannen_dataset) -> Dataset:
    """Make sure gebieden + woningbouwplannen is always combined,
    because woningbouwplannen has a reverse dependency on 'gebieden'.
    This avoids accidentally leaving out the reverse dependency.
    """
    return _gebieden_dataset


@pytest.fixture()
def bag_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("bag.json")


@pytest.fixture()
def bag_dataset(gebieden_dataset, bag_schema) -> Dataset:
    return Dataset.create_for_schema(bag_schema)


@pytest.fixture()
def woningbouwplannen_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("woningbouwplannen.json")


@pytest.fixture()
def woningbouwplannen_dataset(woningbouwplannen_schema, _gebieden_dataset) -> Dataset:
    # Woningbouwplannen has a dependency on gebieden,
    # so this fixture makes sure it's always loaded.
    return Dataset.create_for_schema(woningbouwplannen_schema)


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
def verblijfsobjecten_model(bag_dataset, dynamic_models):
    return dynamic_models["bag"]["verblijfsobjecten"]


@pytest.fixture()
def nummeraanduidingen_model(bag_dataset, dynamic_models):
    return dynamic_models["bag"]["nummeraanduidingen"]


@pytest.fixture()
def bouwblokken_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["bouwblokken"]


@pytest.fixture()
def buurten_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["buurten"]


@pytest.fixture()
def wijken_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["wijken"]


@pytest.fixture()
def stadsdelen_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["stadsdelen"]


@pytest.fixture()
def ggwgebieden_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["ggwgebieden"]


@pytest.fixture()
def ggpgebieden_model(gebieden_dataset, dynamic_models):
    return dynamic_models["gebieden"]["ggpgebieden"]


@pytest.fixture()
def woningbouwplan_model(woningbouwplannen_dataset, dynamic_models):
    return dynamic_models["woningbouwplannen"]["woningbouwplan"]


@pytest.fixture()
def temporal_auth_dataset(schema_loader):
    return Dataset.create_for_schema(schema_loader.get_dataset_from_file("temporal_auth.json"))


@pytest.fixture()
def temporal_auth_model(temporal_auth_dataset, dynamic_models):
    return dynamic_models["temporalauth"]["things"]


@pytest.fixture()
def nontemporeel_model(woningbouwplannen_dataset, dynamic_models):
    return dynamic_models["woningbouwplannen"]["nontemporeel"]


@pytest.fixture()
def statistieken_data(statistieken_model, buurten_data):
    return statistieken_model.objects.create(
        id=1,
        buurt_id="03630000000078",
    )


@pytest.fixture()
def buurten_data(buurten_model) -> DynamicModel:
    # NOTE: 'wijken_data' is not included as fixture here.
    # some tests appear to rely on having a broken relation.
    buurten_model.objects.create(
        id="03630000000078.1",
        identificatie="03630000000078",
        volgnummer=1,
        naam="AAA v1",
        begin_geldigheid=DATE_2021_FEB,
        eind_geldigheid=DATE_2021_JUNE,  # Historical record!
        ligt_in_wijk_id="03630012052035.1",
        ligt_in_wijk_identificatie="03630012052035",
        ligt_in_wijk_volgnummer="1",
    )
    return buurten_model.objects.create(
        id="03630000000078.2",
        identificatie="03630000000078",
        volgnummer=2,
        naam="AAA v2",
        begin_geldigheid=DATE_2021_JUNE,
        ligt_in_wijk_id="03630012052035.1",
        ligt_in_wijk_identificatie="03630012052035",
        ligt_in_wijk_volgnummer="1",
    )


@pytest.fixture()
def bouwblokken_data(bouwblokken_model, buurten_data) -> DynamicModel:
    return bouwblokken_model.objects.create(
        id="03630012096483.1",
        identificatie="03630012096483",
        volgnummer=1,
        begin_geldigheid=DATE_2021_FEB,
        ligt_in_buurt_id="03630000000078.2",  # example (not actual)
        ligt_in_buurt_identificatie="03630000000078",
        ligt_in_buurt_volgnummer="2",
    )


@pytest.fixture()
def panden_data(panden_model, dossiers_model, bouwblokken_data):
    panden_model.objects.create(
        id="0363100012061164.3",
        identificatie="0363100012061164",
        volgnummer=3,
        begin_geldigheid=DATE_2021_FEB,
        naam="Voorbeeldpand",
        status_code=7,
        status_omschrijving="Sloopvergunning verleend",
        bag_proces={"code": 1},
        ligt_in_bouwblok_id="03630012096483.1",
        ligt_in_bouwblok_identificatie="03630012096483",
        ligt_in_bouwblok_volgnummer="1",
        heeft_dossier_id="GV00000406",
    )
    panden_model.objects.create(
        id="9999999999999999.9",
        identificatie="9999999999999999",
        volgnummer=3,
        begin_geldigheid=DATE_2021_FEB,
        naam="Pand zonder bouwblok of dossier",
    )
    dossiers_model.objects.create(dossier="GV00000406")


@pytest.fixture()
def wijken_data(wijken_model, stadsdelen_data) -> DynamicModel:
    return wijken_model.objects.create(
        id="03630012052035.1",
        identificatie="03630012052035",
        volgnummer=1,
        begin_geldigheid=DATE_2021_FEB,
        naam="Burgwallen-Nieuwe Zijde",
        code="A01",
        ligt_in_stadsdeel=stadsdelen_data,
        ligt_in_stadsdeel_identificatie=stadsdelen_data.identificatie,
        ligt_in_stadsdeel_volgnummer=stadsdelen_data.volgnummer,
    )


@pytest.fixture()
def stadsdelen_data(stadsdelen_model) -> DynamicModel:
    return stadsdelen_model.objects.create(
        id="03630000000018.1",
        identificatie="03630000000018",
        volgnummer=1,
        begin_geldigheid=DATE_2021_FEB,
        naam="Centrum",
        code="A",
    )


@pytest.fixture()
def ggwgebieden_data(ggwgebieden_model, buurten_data):
    """Test data for 'Gebiedsgerichtwerken - gebieden'."""
    instance = ggwgebieden_model.objects.create(
        id="03630950000000.1",
        identificatie="03630950000000",
        volgnummer=1,
        begin_geldigheid=DATE_2021_FEB,
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        id=11,
        ggwgebieden_id="03630950000000.1",
        ggwgebieden_identificatie="03630950000000",
        ggwgebieden_volgnummer=1,
        bestaat_uit_buurten_id="03630000000078.1",
        bestaat_uit_buurten_identificatie="03630000000078",
        bestaat_uit_buurten_volgnummer=1,
    )
    ggwgebieden_model.bestaat_uit_buurten.through.objects.create(
        id=22,
        ggwgebieden_id="03630950000000.1",
        ggwgebieden_identificatie="03630950000000",
        ggwgebieden_volgnummer=1,
        bestaat_uit_buurten_id="03630000000078.2",
        bestaat_uit_buurten_identificatie="03630000000078",
        bestaat_uit_buurten_volgnummer=2,
    )
    return instance


@pytest.fixture()
def ggpgebieden_data(ggpgebieden_model, buurten_data):
    ggpgebieden_model.objects.create(
        id="03630950000000.1",
        identificatie="03630950000000",
        volgnummer=1,
        begin_geldigheid=DATE_2021_FEB,
    )
    ggpgebieden_model.bestaat_uit_buurten.through.objects.create(
        id="33",
        ggpgebieden_id="03630950000000.1",
        ggpgebieden_identificatie="03630950000000",
        ggpgebieden_volgnummer=1,
        bestaat_uit_buurten_id="03630000000078.2",
        bestaat_uit_buurten_identificatie="03630000000078",
        bestaat_uit_buurten_volgnummer=2,
        begin_geldigheid="2021-03-04",
        eind_geldigheid=None,
    )


@pytest.fixture()
def woningbouwplannen_data(woningbouwplan_model, buurten_data, nontemporeel_model):
    nontemporeel_model.objects.create(sleutel="1234", label="4displayonly")
    woningbouwplan_model.objects.create(id="1")
    woningbouwplan_model.buurten.through.objects.create(
        id=1000,
        woningbouwplan_id="1",
        buurten_id=buurten_data.identificatie,  # NOTE: not a temporal reference!!
    )
    woningbouwplan_model.buurtenregular.through.objects.create(
        id=1000,
        woningbouwplan_id="1",
        buurtenregular_id=buurten_data.id,
        buurtenregular_identificatie=buurten_data.identificatie,
        buurtenregular_volgnummer=buurten_data.volgnummer,
    )
    woningbouwplan_model.nontemporele_nm.through.objects.create(
        id=1000,
        woningbouwplan_id="1",
        nontemporele_nm_id="1234",
    )
    # woningbouwplan_model.objects.create(id="2", testbuurt="03630000000078")
    # woningbouwplan_model.bestaat_uit_buurten.through.objects.create(
    #    woningbouwplan_id="2", bestaat_uit_buurten_id="03630000000078"
    # )


@pytest.fixture()
def profile_loader() -> FileSystemProfileLoader:
    return FileSystemProfileLoader(HERE / "files/profiles")


@pytest.fixture()
def parkeerwacht_profile(profile_loader) -> Profile:
    return Profile.create_for_schema(profile_loader.get_profile("parkeerwacht"))


@pytest.fixture()
def nummeraanduidingen_data(nummeraanduidingen_model):
    nummeraanduidingen_model.objects.create(identificatie="nm1", volgnummer=1, id="a")
    nummeraanduidingen_model.objects.create(identificatie="nm1", volgnummer=2, id="b")
    nummeraanduidingen_model.objects.create(identificatie="nm2", volgnummer=1, id="c")


@pytest.fixture()
def verblijfsobjecten_data(verblijfsobjecten_model, buurten_data, nummeraanduidingen_data):
    """Verblijfsobjecten with hoofdadres and ligtInBuurt FKs populated"""
    verblijfsobjecten_model.objects.create(
        id="a",
        identificatie="vo1",
        volgnummer=1,
        ligt_in_buurt_id="03630000000078.1",
        ligt_in_buurt_identificatie="03630000000078",
        ligt_in_buurt_volgnummer=1,
        heeft_hoofdadres_id="nm1.1",
        heeft_hoofdadres_identificatie="nm1",
        heeft_hoofdadres_volgnummer=1,
    )
    verblijfsobjecten_model.objects.create(
        id="b",
        identificatie="vo2",
        volgnummer=1,
        ligt_in_buurt_id="03630000000078.2",
        ligt_in_buurt_identificatie="03630000000078",
        ligt_in_buurt_volgnummer=2,
        heeft_hoofdadres_id="nm1.2",
        heeft_hoofdadres_identificatie="nm1",
        heeft_hoofdadres_volgnummer=2,
    )
    verblijfsobjecten_model.objects.create(
        id="c",
        identificatie="vo3",
        volgnummer=1,
        ligt_in_buurt_id="03630000000078.2",
        ligt_in_buurt_identificatie="03630000000078",
        ligt_in_buurt_volgnummer=2,
        heeft_hoofdadres_id="nm2.1",
        heeft_hoofdadres_identificatie="nm2",
        heeft_hoofdadres_volgnummer=1,
    )
    verblijfsobjecten_model.objects.create(
        id="d",
        identificatie="vo4",
        volgnummer=1,
        ligt_in_buurt_id="03630000000078.2",
        ligt_in_buurt_identificatie="XXX",
        ligt_in_buurt_volgnummer=6,
        heeft_hoofdadres_id="nm2.1",
        heeft_hoofdadres_identificatie="nm3",
        heeft_hoofdadres_volgnummer=5,
    )
    verblijfsobjecten_model.objects.create(
        id="e",
        identificatie="vo5",
        volgnummer=1,
        ligt_in_buurt_id=None,
        ligt_in_buurt_identificatie=None,
        ligt_in_buurt_volgnummer=None,
        heeft_hoofdadres_id="nm2.1",
        heeft_hoofdadres_identificatie="nm3",
        heeft_hoofdadres_volgnummer=6,
    )


@pytest.fixture(autouse=True)
def disable_apikey_middelware(settings):
    # The apikey middleware sets up a thread that wants
    # to grab signings keys. We remove this middelware.
    try:
        settings.MIDDLEWARE.remove("apikeyclient.ApiKeyMiddleware")
    except ValueError:
        pass


@pytest.fixture()
def monumenten_schema(schema_loader) -> DatasetSchema:
    return schema_loader.get_dataset_from_file("monumenten.json")


@pytest.fixture()
def monumenten_dataset(monumenten_schema) -> Dataset:
    return Dataset.create_for_schema(monumenten_schema)


@pytest.fixture()
def monumenten_models(monumenten_dataset, dynamic_models):
    return dynamic_models["monumenten"]
