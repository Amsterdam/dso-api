from datetime import date

import pytest
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.core.validators import EmailValidator, URLValidator
from schematools.permissions import UserScopes
from schematools.types import ProfileSchema

from dso_api.dynamic_api.serializers import clear_serializer_factory_cache, serializer_factory
from dso_api.dynamic_api.serializers.fields import HALRawIdentifierUrlField
from rest_framework_dso.fields import EmbeddedField
from tests.utils import (
    api_request_with_scopes,
    normalize_data,
    patch_field_auth,
    to_drf_request,
    to_serializer_view,
    unlazy,
)


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    clear_serializer_factory_cache()


@pytest.fixture()
def afval_cluster(afval_cluster_model):
    # Using a 'dot' in the ID on purpose, to test viewset regexp handling.
    return afval_cluster_model.objects.create(id="123.456", status="open")


@pytest.mark.django_db
class TestDynamicSerializer:
    """All tests for the serializer_factory() logic and embedding.

    Note that updating afval.json means the test output here should be updated too.
    """

    @staticmethod
    def test_basic_factory_logic(
        afval_schema,
        afval_cluster_model,
        afval_container_model,
        afval_cluster,
        filled_router,
    ):
        """Prove that the serializer factory properly generates the embedded fields.

        This checks whether the factory generates the proper FK/embedded fields.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))

        # Access real models to perform 'is' test below.
        afval_cluster_model = unlazy(afval_cluster_model)
        afval_container_model = unlazy(afval_container_model)

        # Confirm that the model is the object that Django also has registered
        # (if this differs, create_tables() might be called twice).
        assert afval_cluster_model is apps.get_model("afvalwegingen.clusters")
        assert afval_container_model is apps.get_model("afvalwegingen.containers")

        afval_container = afval_container_model.objects.create(
            id=2,
            cluster_id=afval_cluster.pk,
            serienummer="serie123",
            eigenaar_naam="datapunt",
            datum_creatie=date(2020, 2, 3),
        )

        # Generate serializers from models
        ContainerSerializer = serializer_factory(afval_container_model)
        ClusterSerializer = serializer_factory(afval_cluster_model)

        # Prove that EmbeddedField is created.
        assert set(ContainerSerializer.Meta.embedded_fields.keys()) == {"cluster"}
        embedded_field: EmbeddedField = ContainerSerializer.Meta.embedded_fields["cluster"]
        assert isinstance(embedded_field, EmbeddedField)

        # Prove that the EmbeddedField references the proper models and serializers.
        # This also tests whether there aren't any old references left.
        assert embedded_field.related_model is afval_cluster_model, (
            "Old Django models were still referenced: "
            f"id {id(embedded_field.related_model)} vs "
            f"id {id(afval_cluster_model)} "
            f"(creation counter {embedded_field.related_model.CREATION_COUNTER}"
            f" vs {afval_cluster_model.CREATION_COUNTER})",
        )
        assert embedded_field.serializer_class.__name__ == ClusterSerializer.__name__

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
        )
        data = normalize_data(container_serializer.data)

        assert data == {
            "_links": {
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
                    "title": "123.456",
                    "id": "123.456",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2",
                    "title": "2",
                    "id": 2,
                },
            },
            "clusterId": "123.456",
            "datumCreatie": "2020-02-03",
            "datumLeegmaken": None,
            "eigenaarNaam": "datapunt",
            "geometry": None,
            "id": 2,
            "serienummer": "serie123",
        }

    @staticmethod
    def test_expand(afval_container_model, afval_cluster):
        """Prove expanding works.

        The _embedded section is generated, using the cluster serializer.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        ContainerSerializer = serializer_factory(afval_container_model)
        afval_container = afval_container_model.objects.create(id=2, cluster=afval_cluster)

        # Prove that expands work on object-detail level
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2",
                    "title": "2",
                    "id": 2,
                },
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
                    "title": "123.456",
                    "id": "123.456",
                },
            },
            "id": 2,
            "clusterId": "123.456",
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {
                "cluster": {
                    "_links": {
                        "self": {
                            "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
                            "title": "123.456",
                            "id": "123.456",
                        },
                        "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#clusters",  # noqa: E501
                    },
                    "id": "123.456",
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_expand_none(afval_container_model):
        """Prove that expanding None values doesn't crash.

        The _embedded part has a None value instead.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        ContainerSerializer = serializer_factory(afval_container_model)
        container_without_cluster = afval_container_model.objects.create(
            id=3,
            cluster=None,
        )
        container_serializer = ContainerSerializer(
            container_without_cluster,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/3",
                    "title": "3",
                    "id": 3,
                },
                "cluster": None,
            },
            "id": 3,
            "clusterId": None,
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {"cluster": None},
        }

    @staticmethod
    def test_expand_broken_relation(afval_container_model):
        """Prove that expanded non-existent FK values are not rendered
        but also don't cause the serializer to crash.

        The _embedded part has a None value instead.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        ContainerSerializer = serializer_factory(afval_container_model)
        container_invalid_cluster = afval_container_model.objects.create(
            id=4,
            cluster_id=99,
        )
        container_serializer = ContainerSerializer(
            container_invalid_cluster,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/4",
                    "title": "4",
                    "id": 4,
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "cluster": None,
            },
            "id": 4,
            "clusterId": 99,
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {"cluster": None},
        }

    @staticmethod
    def test_dataset_path(
        afval_dataset,
        afval_container_model,
        afval_cluster,
        afval_cluster_model,
        filled_router,
    ):
        """Prove dataset url sub paths works.

        The schema in _links contains correct URLs.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        afval_dataset.path = "test/" + afval_dataset.path

        # Update dataset in instance cache
        afval_container_model._dataset = afval_dataset
        afval_cluster_model._dataset = afval_dataset
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        afval_container = afval_container_model.objects.create(id=2, cluster=afval_cluster)

        # Prove that expands work on object-detail level
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/test/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2",
                    "title": "2",
                    "id": 2,
                },
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
                    "title": "123.456",
                    "id": "123.456",
                },
            },
            "id": 2,
            "clusterId": "123.456",
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {
                "cluster": {
                    "_links": {
                        "self": {
                            "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
                            "title": "123.456",
                            "id": "123.456",
                        },
                        "schema": "https://schemas.data.amsterdam.nl/datasets/test/afvalwegingen/dataset#clusters",  # noqa: E501
                    },
                    "id": "123.456",
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_pk_with_relation(
        drf_request, aardgasverbruik_dataset, dynamic_models, django_assert_num_queries
    ):
        # Data used only once, creating locally:
        MraLiander = dynamic_models["aardgasverbruik"]["mra_liander"]
        PostcodeRange = dynamic_models["aardgasverbruik"]["mra_statistieken_pcranges"]
        PostcodeRange.objects.create(
            id=MraLiander.objects.create(id="123"), gemiddeld_verbruik=200
        )

        # Prove that the serializer can be constructed
        PostcodeRangeSerializer = serializer_factory(PostcodeRange)

        # Also prove that the optimizations work and the underlying model
        # doesn't have to be fetched to render the _links.id field:
        with django_assert_num_queries(1):
            pc_range = PostcodeRange.objects.get(id="123")
            postcode_serializer = PostcodeRangeSerializer(
                pc_range,
                context={"request": drf_request, "view": to_serializer_view(PostcodeRange)},
            )
            data = normalize_data(postcode_serializer.data)
            assert data == {
                "_links": {
                    "schema": (
                        "https://schemas.data.amsterdam.nl"
                        "/datasets/aardgasverbruik/dataset#mraStatistiekenPcranges"
                    ),
                    "self": {
                        "href": (
                            "http://testserver/v1/aardgasverbruik/mra_statistieken_pcranges/123"
                        ),
                        "id": "123",
                        "title": "123",
                    },
                    "id": {
                        # PK relation is mentioned in the _links field:
                        "href": "http://testserver/v1/aardgasverbruik/mra_liander/123",
                        "id": "123",
                        "title": "123",
                    },
                },
                # Other values:
                "gemiddeldVerbruik": 200.0,
            }

    @staticmethod
    def test_backwards_relation(drf_request, gebieden_models):
        """Show backwards"""
        drf_request.table_temporal_slice = None
        stadsdelen_model = gebieden_models["stadsdelen"]
        wijken_model = gebieden_models["wijken"]
        stadsdeel = stadsdelen_model.objects.create(
            id="0363.1", identificatie="0363", naam="Stadsdeel", volgnummer=1
        )
        wijken_model.objects.create(
            id="03630000000001.1",
            identificatie="03630000000001",
            volgnummer=1,
            ligt_in_stadsdeel=stadsdeel,
        )
        StadsdelenSerializer = serializer_factory(stadsdelen_model)
        stadsdelen_serializer = StadsdelenSerializer(
            stadsdeel,
            context={"request": drf_request, "view": to_serializer_view(stadsdelen_model)},
        )
        data = normalize_data(stadsdelen_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/gebieden/stadsdelen/0363?volgnummer=1",
                    "title": "0363.1",
                    "volgnummer": 1,
                    "identificatie": "0363",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#stadsdelen",
                "wijken": [
                    {
                        "href": "http://testserver/v1/gebieden/wijken/03630000000001?volgnummer=1",
                        "title": "03630000000001.1",
                        "volgnummer": 1,
                        "identificatie": "03630000000001",
                    }
                ],
            },
            "identificatie": "0363",
            "volgnummer": 1,
            "naam": "Stadsdeel",
            "code": None,
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "ligtInGemeenteIdentificatie": None,
            "registratiedatum": None,
            "documentdatum": None,
            "documentnummer": None,
            "geometrie": None,
        }

    @staticmethod
    def test_multiple_backwards_relations(
        drf_request,
        vestiging_adres_model,
        vestiging_vestiging_model,
        vestiging1,
        vestiging2,
        post_adres1,
    ):
        """Show backwards"""
        VestigingSerializer = serializer_factory(vestiging_vestiging_model)

        vestiging_serializer = VestigingSerializer(
            vestiging1,
            context={
                "request": drf_request,
                "view": to_serializer_view(vestiging_vestiging_model),
            },
        )
        data = normalize_data(vestiging_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/1",
                    "title": "1",
                    "id": 1,
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#vestiging",  # noqa: E501
                "postAdres": {
                    "href": "http://testserver/v1/vestiging/adres/3",
                    "title": "3",
                    "id": 3,
                },
                "bezoekAdres": {
                    "href": "http://testserver/v1/vestiging/adres/1",
                    "title": "1",
                    "id": 1,
                },
            },
            "id": 1,
            "naam": "Snake Oil",
            "postAdresId": 3,
            "bezoekAdresId": 1,
        }

        vestiging_serializer = VestigingSerializer(
            vestiging2,
            context={
                "request": drf_request,
                "view": to_serializer_view(vestiging_vestiging_model),
            },
        )
        data = normalize_data(vestiging_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/2",
                    "title": "2",
                    "id": 2,
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#vestiging",  # noqa: E501
                "postAdres": {
                    "href": "http://testserver/v1/vestiging/adres/3",
                    "title": "3",
                    "id": 3,
                },
                "bezoekAdres": {
                    "href": "http://testserver/v1/vestiging/adres/2",
                    "title": "2",
                    "id": 2,
                },
            },
            "id": 2,
            "naam": "Haarlemmer olie",
            "postAdresId": 3,
            "bezoekAdresId": 2,
        }

        AdresSerializer = serializer_factory(vestiging_adres_model)
        adres_serializer = AdresSerializer(
            post_adres1,
            context={"request": drf_request, "view": to_serializer_view(vestiging_adres_model)},
        )
        data = normalize_data(adres_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#adres",
                "self": {
                    "href": "http://testserver/v1/vestiging/adres/3",
                    "title": "3",
                    "id": 3,
                },
                "vestigingenBezoek": [],
                "vestigingenPost": [
                    {
                        "href": "http://testserver/v1/vestiging/vestiging/1",
                        "title": "1",
                        "id": 1,
                    },
                    {
                        "href": "http://testserver/v1/vestiging/vestiging/2",
                        "title": "2",
                        "id": 2,
                    },
                ],
            },
            "id": 3,
            "nummer": 1,
            "plaats": "Amsterdam",
            "postcode": "1000AA",
            "straat": "Dam",
        }

    @staticmethod
    def test_serializer_has_nested_table(
        drf_request, parkeervakken_parkeervak_model, parkeervakken_regime_model
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        parkeervak = parkeervakken_parkeervak_model.objects.create(
            id="121138489047",
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
            buurtcode="A05d",
            straatnaam="Zoutkeetsgracht",
        )
        parkeervakken_regime_model.objects.create(
            id=1,
            parent=parkeervak,
            bord="",
            dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="69-SF-NT",
            opmerking="",
            eindtijd="23:59:00",
            begintijd="00:00:00",
            einddatum=None,
            begindatum=None,
        )

        ParkeervakSerializer = serializer_factory(parkeervakken_parkeervak_model)

        # Prove that no reverse relation to containers here.
        assert "regimes" in ParkeervakSerializer._declared_fields

        # Prove that data is serialized with relations.

        parkeervak_serializer = ParkeervakSerializer(
            parkeervak,
            context={
                "request": drf_request,
                "view": to_serializer_view(parkeervakken_parkeervak_model),
            },
        )
        data = normalize_data(parkeervak_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/121138489047",
                    "id": "121138489047",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/parkeervakken/dataset#parkeervakken",  # noqa: E501
            },
            "geometry": None,
            "id": "121138489047",
            "type": "File",
            "soort": "MULDER",
            "aantal": 1.0,
            "eType": "E9",
            "buurtcode": "A05d",
            "straatnaam": "Zoutkeetsgracht",
            "volgnummer": None,
            "regimes": [
                {
                    "bord": "",
                    "dagen": ["ma", "di", "wo", "do", "vr", "za", "zo"],
                    "soort": "MULDER",
                    "aantal": None,
                    "eType": "E6b",
                    "kenteken": "69-SF-NT",
                    "eindtijd": "23:59:00",
                    "opmerking": "",
                    "begintijd": "00:00:00",
                    "einddatum": None,
                    "begindatum": None,
                }
            ],
        }

    @staticmethod
    def test_display_title_present(drf_request, fietspaaltjes_model, fietspaaltjes_data):
        """Prove that title element shows display value if display field is specified"""

        FietsplaatjesSerializer = serializer_factory(fietspaaltjes_model)

        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data,
            context={"request": drf_request, "view": to_serializer_view(fietspaaltjes_model)},
        )

        assert "'title': 'reference for DISPLAY FIELD'" in str(fietsplaatjes_serializer.data)

    @staticmethod
    def test_no_display_title_present(
        drf_request, fietspaaltjes_model_no_display, fietspaaltjes_data_no_display
    ):
        """Prove that title element is omitted if display field is not specified"""

        FietsplaatjesSerializer = serializer_factory(fietspaaltjes_model_no_display)
        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data_no_display,
            context={
                "request": drf_request,
                "view": to_serializer_view(fietspaaltjes_model_no_display),
            },
        )

        assert "'title', 'reference for DISPLAY FIELD'" not in str(fietsplaatjes_serializer.data)

    @staticmethod
    def test_uri_field_present(explosieven_model):
        """Prove that a URLfield is stored as a charfield and default 200 in length"""
        assert explosieven_model._meta.get_field("pdf").get_internal_type() == "CharField"
        assert explosieven_model._meta.get_field("pdf").max_length == 200

    @staticmethod
    def test_uri_field_can_validate(drf_request, explosieven_model, explosieven_data):
        """Prove that a URLfield can be validated by the URIValidator"""

        ExplosievenSerializer = serializer_factory(explosieven_model)
        explosieven_serializer = ExplosievenSerializer(
            explosieven_data,
            context={"request": drf_request, "view": to_serializer_view(explosieven_model)},
        )

        # Validation passes if outcome is None
        assert URLValidator()(explosieven_serializer.data["pdf"]) is None

    @staticmethod
    def test_uri_field_is_URL_encoded(drf_request, explosieven_model, explosieven_data):
        """Prove that a URLfield content is URL encoded i.e. space to %20"""

        ExplosievenSerializer = serializer_factory(explosieven_model)
        explosieven_serializer = ExplosievenSerializer(
            explosieven_data,
            context={"request": drf_request, "view": to_serializer_view(explosieven_model)},
        )

        # Validation passes if a space does not exists (translated to %20)
        assert " " not in str(explosieven_serializer.data["pdf"]) and "%20" in str(
            explosieven_serializer.data["pdf"]
        )

    @staticmethod
    def test_email_field_can_validate_with_validator(
        drf_request, explosieven_model, explosieven_data
    ):
        """Prove that a EmailField can be validated by the EmailValidator"""

        ExplosievenSerializer = serializer_factory(explosieven_model)
        explosieven_serializer = ExplosievenSerializer(
            explosieven_data,
            context={"request": drf_request, "view": to_serializer_view(explosieven_model)},
        )

        # Validation passes if outcome is None
        assert EmailValidator()(explosieven_serializer.data["emailadres"]) is None

    @staticmethod
    def test_indirect_self_reference(ligplaatsen_model, filled_router):
        """Prove that a dataset with two tables that
        are mutually related generates a serialize without any problems
        (no infinite recursion)
        """
        serializer_factory(ligplaatsen_model)

    @staticmethod
    def test_auth_link_item(drf_request, afval_container_model, afval_container):
        """Prove that the ``_links`` field also handles permissions."""
        ContainerSerializer = serializer_factory(afval_container_model)
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                # The cluster block is completely omitted because there is no access to the table.
                # Just showing the href would leak the identifier. Setting "cluster": null
                # would be ambiguous, since that already means "no cluster for this container".
                #
                # "cluster": {
                #     "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                #     "title": "123.456",
                #     "id": "123.456",
                # },
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/1",
                    "title": "1",
                    "id": 1,
                },
            },
            "clusterId": "123.456",
            "datumCreatie": "2021-01-03",
            "datumLeegmaken": "2021-01-03T11:13:14",
            "eigenaarNaam": "Dataservices",
            "geometry": {"coordinates": [10.0, 10.0], "type": "Point"},
            "id": 1,
            "serienummer": "foobar-123",
        }

        # And again with scopes
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request, "view": to_serializer_view(afval_container_model)},
        )
        data = normalize_data(container_serializer.data)
        assert data["_links"]["cluster"] == {
            "href": "http://testserver/v1/afvalwegingen/clusters/123.456",
            "title": "123.456",
            "id": "123.456",
        }

    @staticmethod
    def test_profile_display_first_letter(
        drf_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """Prove that only first letter is seen in Profile allows only it."""
        # does not have scope for Dataset or Table
        drf_request.user_scopes = UserScopes(
            {},
            request_scopes=[],
            all_profiles=[
                ProfileSchema.from_dict(
                    {
                        "name": "only_first",
                        "datasets": {
                            "fietspaaltjes": {
                                "tables": {
                                    "fietspaaltjes": {
                                        "fields": {"area": "letters:1"},
                                    }
                                }
                            }
                        },
                    }
                ),
            ],
        )

        # Make sure the field is not readable by default, so profiles are activated
        patch_field_auth(fietspaaltjes_schema, "fietspaaltjes", "area", auth=["FOO/BAR"])
        assert drf_request.user_scopes.get_active_profile_datasets("fietspaaltjes")

        FietspaaltjesSerializer = serializer_factory(fietspaaltjes_model)
        fietspaaltjes_serializer = FietspaaltjesSerializer(
            fietspaaltjes_data,
            context={"request": drf_request, "view": to_serializer_view(fietspaaltjes_model)},
        )

        assert fietspaaltjes_serializer.data["area"] == "A"

    @staticmethod
    def test_profile_display_first_letter_many(
        drf_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """Prove that only first letter is seen in Profile allows only it in listing."""
        drf_request.user_scopes = UserScopes(
            {},
            request_scopes=[],
            all_profiles=[
                ProfileSchema.from_dict(
                    {
                        "name": "only_first",
                        "datasets": {
                            "fietspaaltjes": {
                                "tables": {
                                    "fietspaaltjes": {
                                        "fields": {"area": "letters:1"},
                                    }
                                }
                            }
                        },
                    }
                )
            ],
        )

        # Make sure the field is not readable by default, so profiles are activated
        patch_field_auth(fietspaaltjes_schema, "fietspaaltjes", "area", auth=["FOO/BAR"])

        FietspaaltjesSerializer = serializer_factory(fietspaaltjes_model)
        fietspaaltjes_serializer = FietspaaltjesSerializer(
            fietspaaltjes_model.objects.all(),
            context={"request": drf_request, "view": to_serializer_view(fietspaaltjes_model)},
            many=True,
        )

        fietspaaltjes = list(fietspaaltjes_serializer.data["fietspaaltjes"])  # consume generator
        assert fietspaaltjes[0]["area"] == "A", fietspaaltjes_serializer.data

    @staticmethod
    def test_loose_relation_serialization(drf_request, statistieken_model):
        """Prove that the serializer factory generates the right link
        for a loose relation field
        """
        statistiek = statistieken_model.objects.create(
            id=1,
            buurt_id="03630000000078",
        )
        StatistiekenSerializer = serializer_factory(statistieken_model)

        statistieken_serializer = StatistiekenSerializer(
            statistiek,
            context={"request": drf_request, "view": to_serializer_view(statistieken_model)},
        )
        buurt_field = statistieken_serializer.fields["_links"].fields["buurt"]
        assert buurt_field.__class__.__name__ == "GebiedenBuurtenRawIdentifierSerializer"
        assert isinstance(buurt_field.fields["href"], HALRawIdentifierUrlField)

        assert (
            statistieken_serializer.data["_links"]["buurt"]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078"
        ), statistieken_serializer.data

    @staticmethod
    def test_unconventional_temporal_identifier(drf_request, unconventional_temporal_model):
        """Prove that temporal ids with casing and shortnames are properly serialized"""
        obj = unconventional_temporal_model.objects.create(
            unconventional_identifier=1,  # also the primary key!
            unconventional_temporal_id="v1",
            begin_geldigheid="2020-01-01",
            eind_geldigheid="2021-01-01",
        )
        serializer_class = serializer_factory(unconventional_temporal_model)
        serializer = serializer_class(
            obj,
            context={
                "request": drf_request,
                "view": to_serializer_view(unconventional_temporal_model),
            },
        )

        fields = serializer.fields
        assert set(fields.keys()) == {
            "_links",
            "unconventionalIdentifier",
            "unconventionalTemporalId",
            "beginGeldigheid",
            "eindGeldigheid",
        }

        # assert fields["unconventionalIdentifier"].source == "uncid"
        assert fields["unconventionalTemporalId"].source == "unconventional_temporal_id"
        assert fields["eindGeldigheid"].source == "eind_geldigheid"
        assert fields["beginGeldigheid"].source == "begin_geldigheid"
        assert (
            fields["_links"]["self"]["unconventionalIdentifier"].source
            == "unconventional_identifier"
        )
        assert (
            fields["_links"]["self"]["unconventionalTemporalId"].source
            == "unconventional_temporal_id"
        )

    @staticmethod
    def test_skipping_protected_relations(drf_request, monumenten_models):
        """Prove that protected relations are skipped in the output."""

        monumenten_model = monumenten_models["monumenten"]
        complexen_model = monumenten_models["complexen"]
        ComplexenSerializer = serializer_factory(complexen_model)
        MonumentenSerializer = serializer_factory(monumenten_model)
        monumenten_data = monumenten_model.objects.create(
            identificatie="AB.CD",
            monumentnummer=1,
            beschrijving="oud gebouw",
        )
        complexen_data = complexen_model.objects.create(
            identificatie="AB",
            naam="Paleis",
            beschrijving="prachtig complex (geheim)",
            beschrijving_publiek="prachtig complex",
        )
        monumenten_data.ligt_in_monumenten_complex = complexen_data
        complexen_data.bestaat_uit_monumenten_monumenten.set([monumenten_data])

        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        complexen_serializer = ComplexenSerializer(
            complexen_data,
            context={"request": drf_request, "view": to_serializer_view(complexen_model)},
        )

        monumenten_serializer = MonumentenSerializer(
            monumenten_data,
            context={"request": drf_request, "view": to_serializer_view(monumenten_model)},
        )

        # Because the monumenten schema has on protected field,
        # the M2M link to monumenten will no be available in the output.
        data = normalize_data(complexen_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/monumenten/dataset#complexen",
                "self": {
                    "href": "http://testserver/v1/monumenten/complexen/AB",
                    "identificatie": "AB",
                    "title": "AB",
                },
            },
            "beschrijvingPubliek": "prachtig complex",
            "identificatie": "AB",
            "naam": "Paleis",
        }

        data = normalize_data(monumenten_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/monumenten/dataset#monumenten",
                "self": {
                    "href": "http://testserver/v1/monumenten/monumenten/AB.CD",
                    "identificatie": "AB.CD",
                    "title": "AB.CD",
                },
            },
            "identificatie": "AB.CD",
            "ligtInMonumentenComplexId": "AB",
            "monumentnummer": 1,
        }

    @staticmethod
    def test_getting_protected_relations_when_using_scope(monumenten_models):
        """Prove that protected relations are available in the output
        when request has the right scope."""

        monumenten_model = monumenten_models["monumenten"]
        complexen_model = monumenten_models["complexen"]
        ComplexenSerializer = serializer_factory(complexen_model)
        MonumentenSerializer = serializer_factory(monumenten_model)
        monumenten_data = monumenten_model.objects.create(
            identificatie="AB.CD",
            monumentnummer=1,
            beschrijving="oud gebouw",
        )
        complexen_data = complexen_model.objects.create(
            identificatie="AB",
            naam="Paleis",
            beschrijving="prachtig complex (geheim)",
            beschrijving_publiek="prachtig complex",
        )
        monumenten_data.ligt_in_monumenten_complex = complexen_data
        complexen_data.bestaat_uit_monumenten_monumenten.set([monumenten_data])

        drf_request = to_drf_request(api_request_with_scopes(["MON/RDM"]))
        complexen_serializer = ComplexenSerializer(
            complexen_data,
            context={"request": drf_request, "view": to_serializer_view(complexen_model)},
        )

        monumenten_serializer = MonumentenSerializer(
            monumenten_data,
            context={"request": drf_request, "view": to_serializer_view(monumenten_model)},
        )

        # Because the monumenten schema has on protected field,
        # the M2M link to monumenten will no be available in the output.
        data = normalize_data(complexen_serializer.data)
        assert data == {
            "_links": {
                "bestaatUitMonumentenMonumenten": [
                    {
                        "href": "http://testserver/v1/monumenten/monumenten/AB.CD",
                        "identificatie": "AB.CD",
                        "title": "AB.CD",
                    }
                ],
                "schema": "https://schemas.data.amsterdam.nl/"
                "datasets/monumenten/dataset#complexen",
                "self": {
                    "href": "http://testserver/v1/monumenten/complexen/AB",
                    "identificatie": "AB",
                    "title": "AB",
                },
            },
            "beschrijving": "prachtig complex (geheim)",
            "beschrijvingPubliek": "prachtig complex",
            "identificatie": "AB",
            "naam": "Paleis",
        }

        data = normalize_data(monumenten_serializer.data)
        assert data == {
            "_links": {
                "ligtInMonumentenComplex": {
                    "href": "http://testserver/v1/monumenten/complexen/AB",
                    "identificatie": "AB",
                    "title": "AB",
                },
                "schema": "https://schemas.data.amsterdam.nl/"
                "datasets/monumenten/dataset#monumenten",
                "self": {
                    "href": "http://testserver/v1/monumenten/monumenten/AB.CD",
                    "identificatie": "AB.CD",
                    "title": "AB.CD",
                },
            },
            "beschrijving": "oud gebouw",
            "identificatie": "AB.CD",
            "ligtInMonumentenComplexId": "AB",
            "monumentnummer": 1,
        }

    @staticmethod
    def test_request_unprotected_fields_without_scopes_should_be_allowed(
        drf_request, monumenten_models
    ):
        """Prove that unprotected fields can be fetched without scopes."""

        monumenten_model = monumenten_models["monumenten"]
        complexen_model = monumenten_models["complexen"]
        MonumentenSerializer = serializer_factory(monumenten_model)
        monumenten_data = monumenten_model.objects.create(
            identificatie="AB.CD",
            monumentnummer=1,
            beschrijving="oud gebouw",
        )
        complexen_data = complexen_model.objects.create(
            identificatie="AB",
            naam="Paleis",
            beschrijving="prachtig complex (geheim)",
            beschrijving_publiek="prachtig complex",
        )
        monumenten_data.ligt_in_monumenten_complex = complexen_data
        complexen_data.bestaat_uit_monumenten_monumenten.set([monumenten_data])

        # Nasty trick to avoid fetching prefetched data.
        # When prefetching, the `DynamicSerializer.get_embedded_objects_by_id`
        # is not touched.
        monumenten_data._state.fields_cache.clear()
        complexen_data._state.fields_cache.clear()

        # We also add a camelCased name to the `_fields`, because this
        # needs an extra snakecasing treatment in the code to work properly.
        drf_request = to_drf_request(
            api_request_with_scopes(
                [],
                data={
                    "_expandScope": "ligtInMonumentenComplex",
                    "_fields": "ligtInMonumentenComplex.naam,"
                    "ligtInMonumentenComplex.beschrijvingPubliek",
                },
            )
        )

        monumenten_serializer = MonumentenSerializer(
            monumenten_data,
            context={"request": drf_request, "view": to_serializer_view(monumenten_model)},
        )

        data = normalize_data(monumenten_serializer.data)

        assert data == {
            "_embedded": {
                "ligtInMonumentenComplex": {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets"
                        "/monumenten/dataset#complexen",
                        "self": {
                            "href": "http://testserver/v1/monumenten/complexen/AB",
                            "identificatie": "AB",
                            "title": "AB",
                        },
                    },
                    "beschrijvingPubliek": "prachtig complex",
                    "naam": "Paleis",
                }
            },
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets"
                "/monumenten/dataset#monumenten",
                "self": {
                    "href": "http://testserver/v1/monumenten/monumenten/AB.CD",
                    "identificatie": "AB.CD",
                    "title": "AB.CD",
                },
            },
            "identificatie": "AB.CD",
            "ligtInMonumentenComplexId": "AB",
            "monumentnummer": 1,
        }

    @staticmethod
    def test_request_protected_fields_without_scopes_should_not_be_allowed(
        drf_request, monumenten_models
    ):
        """Prove that protected fields cannot be fetched without scopes."""

        monumenten_model = monumenten_models["monumenten"]
        complexen_model = monumenten_models["complexen"]
        MonumentenSerializer = serializer_factory(monumenten_model)
        monumenten_data = monumenten_model.objects.create(
            identificatie="AB.CD",
            monumentnummer=1,
            beschrijving="oud gebouw",
        )
        complexen_data = complexen_model.objects.create(
            identificatie="AB",
            naam="Paleis",
            beschrijving="prachtig complex",
        )
        monumenten_data.ligt_in_monumenten_complex = complexen_data
        complexen_data.bestaat_uit_monumenten_monumenten.set([monumenten_data])

        drf_request = to_drf_request(
            api_request_with_scopes(
                [],
                data={
                    "_expandScope": "ligtInMonumentenComplex",
                    "_fields": "ligtInMonumentenComplex.beschrijving",
                },
            )
        )

        monumenten_serializer = MonumentenSerializer(
            monumenten_data,
            context={"request": drf_request, "view": to_serializer_view(monumenten_model)},
        )

        # Trying to fetch the data (Serializer tries to render the data)
        # should not be allowed.
        with pytest.raises(PermissionDenied):
            monumenten_serializer.data  # noqa: B018

    @staticmethod
    def test_request_expand_scope_for_protected_expand_should_not_be_allowed(
        drf_request, monumenten_models
    ):
        """Prove that the full table (not `_fields`) cannot be fetched without scopes."""

        monumenten_model = monumenten_models["monumenten"]
        complexen_model = monumenten_models["complexen"]
        MonumentenSerializer = serializer_factory(monumenten_model)
        monumenten_data = monumenten_model.objects.create(
            identificatie="AB.CD",
            monumentnummer=1,
            beschrijving="oud gebouw",
        )
        complexen_data = complexen_model.objects.create(
            identificatie="AB",
            naam="Paleis",
            beschrijving="prachtig complex",
        )
        monumenten_data.ligt_in_monumenten_complex = complexen_data
        complexen_data.bestaat_uit_monumenten_monumenten.set([monumenten_data])

        drf_request = to_drf_request(
            api_request_with_scopes(
                [],
                data={
                    "_expandScope": "ligtInMonumentenComplex",
                },
            )
        )

        monumenten_serializer = MonumentenSerializer(
            monumenten_data,
            context={"request": drf_request, "view": to_serializer_view(monumenten_model)},
        )

        # Trying to fetch the data (Serializer tries to render the data)
        # should not be allowed.
        with pytest.raises(PermissionDenied):
            monumenten_serializer.data  # noqa: B018
