import pytest
from collections import OrderedDict
from datetime import date

from django.core.validators import URLValidator
from django.core.validators import EmailValidator

from rest_framework_dso.fields import EmbeddedField
from schematools.contrib.django.auth_backend import RequestProfile
from schematools.contrib.django.models import Profile
from dso_api.dynamic_api.serializers import serializer_factory


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    serializer_factory.cache_clear()


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
        api_request,
        afval_schema,
        afval_cluster_model,
        afval_container_model,
        afval_cluster,
    ):
        """Prove that the serializer factory properly generates the embedded fields.

        This checks whether the factory generates the proper FK/embedded fields.
        """
        api_request.dataset = afval_schema
        afval_container = afval_container_model.objects.create(
            id=2,
            cluster=afval_cluster,
            serienummer="serie123",
            eigenaar_naam="datapunt",
            datum_creatie=date(2020, 2, 3),
        )

        # Generate serializers from models
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        # Important note is that ClusterSerializer is initiated as flat,
        # not allowing relations to resolve.
        ClusterSerializer = serializer_factory(afval_cluster_model, 0, flat=True)

        # Prove that EmbeddedField is created, as it should be.
        assert ContainerSerializer.Meta.embedded_fields == ["cluster"]
        assert isinstance(ContainerSerializer.cluster, EmbeddedField)
        assert ContainerSerializer.cluster.related_model is afval_cluster_model
        assert (
            ContainerSerializer.cluster.serializer_class.__name__
            == ClusterSerializer.__name__
        )

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        container_serializer = ContainerSerializer(
            afval_container, context={"request": api_request}
        )
        assert container_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "2",
                }
            },
            "id": 2,
            "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#containers",  # noqa: E501
            "clusterId": "123.456",
            "cluster": "http://testserver/v1/afvalwegingen/clusters/123.456/",
            "serienummer": "serie123",
            "datumCreatie": "2020-02-03",
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": "datapunt",
        }

    @staticmethod
    def test_expand(api_request, afval_schema, afval_container_model, afval_cluster):
        """Prove expanding works.

        The _embedded section is generated, using the cluster serializer.
        """
        api_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        afval_container = afval_container_model.objects.create(
            id=2, cluster=afval_cluster
        )

        # Prove that expands work on object-detail level
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": api_request},
            fields_to_expand=["cluster"],
        )
        assert container_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "2",
                }
            },
            "id": 2,
            "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#containers",  # noqa: E501
            "clusterId": "123.456",
            "cluster": "http://testserver/v1/afvalwegingen/clusters/123.456/",
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {
                "cluster": {
                    "_links": {
                        "self": {
                            "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                            "title": "123.456",
                        }
                    },
                    "id": "123.456",
                    "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#clusters",  # noqa: E501
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_expand_none(api_request, afval_schema, afval_container_model):
        """Prove that expanding None values doesn't crash.

        The _embedded part has a None value instead.
        """
        api_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        container_without_cluster = afval_container_model.objects.create(
            id=3, cluster=None,
        )
        container_serializer = ContainerSerializer(
            container_without_cluster,
            context={"request": api_request},
            fields_to_expand=["cluster"],
        )
        assert container_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/3/",
                    "title": "3",
                }
            },
            "id": 3,
            "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#containers",  # noqa: E501
            "clusterId": None,
            "cluster": None,
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {"cluster": None},
        }

    @staticmethod
    def test_expand_broken_relation(api_request, afval_schema, afval_container_model):
        """Prove that expanding non-existing FK values values doesn't crash.
           Cluster will not be expanded to a url, because the pk_only_optimization
           has been switched off for hyperlinked related fields.
        The _embedded part has a None value instead.
        """
        api_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        container_invalid_cluster = afval_container_model.objects.create(
            id=4, cluster_id=99,
        )
        container_serializer = ContainerSerializer(
            container_invalid_cluster,
            context={"request": api_request},
            fields_to_expand=["cluster"],
        )
        assert container_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/4/",
                    "title": "4",
                }
            },
            "id": 4,
            "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#containers",  # noqa: E501
            "clusterId": 99,
            "cluster": "http://testserver/v1/afvalwegingen/clusters/99/",
            "serienummer": None,
            "datumCreatie": None,
            "datumLeegmaken": None,
            "geometry": None,
            "eigenaarNaam": None,
            "_embedded": {"cluster": None},
        }

    @staticmethod
    def test_backwards_relation(
        api_request,
        bagh_schema,
        bagh_gemeente_model,
        bagh_stadsdeel_model,
        bagh_gemeente,
        bagh_stadsdeel,
    ):
        """Show backwards

        The _embedded part has a None value instead.
        """
        api_request.dataset = bagh_schema
        api_request.dataset_temporal_slice = None
        GemeenteSerializer = serializer_factory(bagh_gemeente_model, 0)
        gemeente_serializer = GemeenteSerializer(
            bagh_gemeente, context={"request": api_request},
        )
        assert gemeente_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/bagh/gemeente/0363/?volgnummer=1",
                    "title": "0363_001",
                }
            },
            "schema": "https://schemas.data.amsterdam.nl/datasets/bagh/bagh#gemeente",
            "stadsdelen": [
                "http://testserver/v1/bagh/stadsdeel/03630000000001/?volgnummer=001",
            ],
            "id": "0363_001",
            "naam": "Amsterdam",
            "volgnummer": 1,
            "identificatie": "0363",
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "registratiedatum": None,
            "verzorgingsgebied": None,
        }

    @staticmethod
    def test_multiple_backwards_relations(
        api_request,
        vestiging_schema,
        vestiging_adres_model,
        vestiging_vestiging_model,
        vestiging1,
        vestiging2,
        post_adres1,
    ):
        """Show backwards

        The _embedded part has a None value instead.
        """
        api_request.dataset = vestiging_schema

        VestigingSerializer = serializer_factory(vestiging_vestiging_model, 0)

        vestiging_serializer = VestigingSerializer(
            vestiging1, context={"request": api_request},
        )

        assert vestiging_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/1/",
                    "title": "1",
                }
            },
            "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/vestiging#vestiging",
            "id": 1,
            "naam": "Snake Oil",
            "postAdresId": 3,
            "postAdres": "http://testserver/v1/vestiging/adres/3/",
            "bezoekAdresId": 1,
            "bezoekAdres": "http://testserver/v1/vestiging/adres/1/",
        }

        vestiging_serializer = VestigingSerializer(
            vestiging2, context={"request": api_request},
        )
        assert vestiging_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/2/",
                    "title": "2",
                }
            },
            "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/vestiging#vestiging",
            "id": 2,
            "naam": "Haarlemmer olie",
            "postAdresId": 3,
            "postAdres": "http://testserver/v1/vestiging/adres/3/",
            "bezoekAdresId": 2,
            "bezoekAdres": "http://testserver/v1/vestiging/adres/2/",
        }

        AdresSerializer = serializer_factory(vestiging_adres_model, 0)
        adres_serializer = AdresSerializer(
            post_adres1, context={"request": api_request},
        )
        assert adres_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/adres/3/",
                    "title": "3",
                }
            },
            "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/vestiging#adres",
            "vestigingenBezoek": [],
            "vestigingenPost": [
                "http://testserver/v1/vestiging/vestiging/1/",
                "http://testserver/v1/vestiging/vestiging/2/",
            ],
            "id": 3,
            "nummer": 1,
            "plaats": "Amsterdam",
            "straat": "Dam",
            "postcode": "1000AA",
        }

    @staticmethod
    def test_serializer_has_nested_table(
        api_request,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        api_request.dataset = parkeervakken_schema
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
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None,
        )

        ParkeervaakSerializer = serializer_factory(parkeervakken_parkeervak_model, 0)

        # Prove that no reverse relation to containers here.
        assert "regimes" in ParkeervaakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        parkeervaak_serializer = ParkeervaakSerializer(
            parkeervak, context={"request": api_request}
        )
        assert parkeervaak_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/121138489047/",
                }
            },
            "geometry": None,
            "id": "121138489047",
            "schema": "https://schemas.data.amsterdam.nl/datasets/parkeervakken/parkeervakken#parkeervakken",  # noqa: E501
            "type": "File",
            "soort": "MULDER",
            "aantal": 1.0,
            "eType": "E9",
            "buurtcode": "A05d",
            "straatnaam": "Zoutkeetsgracht",
            "regimes": [
                OrderedDict(
                    bord="",
                    dagen=["ma", "di", "wo", "do", "vr", "za", "zo"],
                    soort="MULDER",
                    aantal=None,
                    eType="E6b",
                    kenteken="69-SF-NT",
                    eindTijd="23:59:00",
                    opmerking="",
                    beginTijd="00:00:00",
                    eindDatum=None,
                    beginDatum=None,
                )
            ],
        }

    @staticmethod
    def test_flat_serializer_has_no_nested_table(
        api_request,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
    ):
        """Prove that the serializer factory properly skipping generation of reverse
        relations if `flat=True`.
        Flat serialiser should not contain any reverse relations,
        as flat serializers are used to represet instances of sub-serializers.
        """
        api_request.dataset = parkeervakken_schema
        parkeervak = parkeervakken_parkeervak_model.objects.create(
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
            buurtcode="A05d",
            id="121138489047",
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
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None,
        )

        ParkeervaakSerializer = serializer_factory(
            parkeervakken_parkeervak_model, 0, flat=True
        )

        # Prove that no reverse relation to containers here.
        assert "regimes" not in ParkeervaakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        parkeervaak_serializer = ParkeervaakSerializer(
            parkeervak, context={"request": api_request}
        )
        assert parkeervaak_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/121138489047/"
                }
            },
            "geometry": None,
            "id": "121138489047",
            "schema": "https://schemas.data.amsterdam.nl/datasets/parkeervakken/parkeervakken#parkeervakken",  # noqa: E501
            "type": "File",
            "soort": "MULDER",
            "aantal": 1.0,
            "eType": "E9",
            "buurtcode": "A05d",
            "straatnaam": "Zoutkeetsgracht",
        }

    @staticmethod
    def test_display_title_present(
        api_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data,
    ):
        """ Prove that title element shows display value if display field is specified """

        FietsplaatjesSerializer = serializer_factory(fietspaaltjes_model, 0, flat=False)

        api_request.dataset = fietspaaltjes_schema

        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data, context={"request": api_request}
        )

        assert "'title': 'reference for DISPLAY FIELD'" in str(
            fietsplaatjes_serializer.data
        )

    @staticmethod
    def test_no_display_title_present(
        api_request,
        fietspaaltjes_schema_no_display,
        fietspaaltjes_model_no_display,
        fietspaaltjes_data_no_display,
    ):
        """ Prove that title element is omitted if display field is not specified """

        FietsplaatjesSerializer = serializer_factory(
            fietspaaltjes_model_no_display, 0, flat=True
        )

        api_request.dataset = fietspaaltjes_schema_no_display

        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data_no_display, context={"request": api_request}
        )

        assert "'title': 'reference for DISPLAY FIELD'" not in str(
            fietsplaatjes_serializer.data
        )

    @staticmethod
    def test_uri_field_present(explosieven_model):
        """ Prove that a URLfield is stored as a charfield and default 200 in length """
        assert (
            explosieven_model._meta.get_field("pdf").get_internal_type() == "CharField"
        )
        assert explosieven_model._meta.get_field("pdf").max_length == 200

    @staticmethod
    def test_uri_field_can_validate(
        api_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a URLfield can be validated by the URIValidator """

        ExplosievenSerializer = serializer_factory(explosieven_model, 0, flat=True)

        api_request.dataset = explosieven_schema

        validate_uri = URLValidator()

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": api_request}
        )

        # Validation passes if outcome is None
        assert validate_uri(explosieven_serializer.data["pdf"]) is None

    @staticmethod
    def test_uri_field_is_URL_encoded(
        api_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a URLfield content is URL encoded i.e. space to %20 """

        ExplosievenSerializer = serializer_factory(explosieven_model, 0, flat=True)

        api_request.dataset = explosieven_schema

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": api_request}
        )

        # Validation passes if a space does not exists (translated to %20)
        assert " " not in str(explosieven_serializer.data["pdf"]) and "%20" in str(
            explosieven_serializer.data["pdf"]
        )

    @staticmethod
    def test_email_field_can_validate_with_validator(
        api_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a EmailField can be validated by the EmailValidator """

        ExplosievenSerializer = serializer_factory(explosieven_model, 0, flat=True)

        api_request.dataset = explosieven_schema

        validate_email = EmailValidator()

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": api_request}
        )

        # Validation passes if outcome is None
        assert validate_email(explosieven_serializer.data["emailadres"]) is None

    @staticmethod
    def test_indirect_self_reference(
        api_request, indirect_self_ref_schema, filled_router
    ):
        """Prove that a dataset with two tables that
        are mutually related generates a serialize without any problems
        (no infinite recursion)
        """
        api_request.dataset = indirect_self_ref_schema
        indirect_self_ref_model = filled_router.all_models["selfref"]["ligplaatsen"]
        serializer_factory(indirect_self_ref_model, 0)

    @staticmethod
    def test_field_permissions_display_first_letter(
        api_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """ Prove that only first letter is seen in Profile allows only it."""

        Profile.objects.create(
            name="test_1",
            scopes="",
            schema_data={
                "datasets": {
                    "fietspaaltjes": {
                        "tables": {"fietspaaltjes": {"fields": {"area": "letters:1"}}}
                    }
                }
            },
        )
        api_request.auth_profile = RequestProfile(api_request)
        api_request.is_authorized_for = lambda scopes: True
        FietspaaltjesSerializer = serializer_factory(fietspaaltjes_model, 0, flat=False)

        api_request.dataset = fietspaaltjes_schema

        fietspaaltjes_serializer = FietspaaltjesSerializer(
            fietspaaltjes_data, context={"request": api_request}
        )

        assert fietspaaltjes_serializer.data["area"] == "A"

    @staticmethod
    def test_field_permissions_display_first_letter_many(
        api_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """ Prove that only first letter is seen in Profile allows only it in listing. """

        Profile.objects.create(
            name="test_1",
            scopes="",
            schema_data={
                "datasets": {
                    "fietspaaltjes": {
                        "tables": {"fietspaaltjes": {"fields": {"area": "letters:1"}}}
                    }
                }
            },
        )
        api_request.auth_profile = RequestProfile(api_request)
        api_request.is_authorized_for = lambda scopes: True
        FietspaaltjesSerializer = serializer_factory(fietspaaltjes_model, 0, flat=False)

        api_request.dataset = fietspaaltjes_schema

        fietspaaltjes_serializer = FietspaaltjesSerializer(
            fietspaaltjes_model.objects.all(),
            context={"request": api_request},
            many=True,
        )

        assert (
            fietspaaltjes_serializer.data["fietspaaltjes"][0]["area"] == "A"
        ), fietspaaltjes_serializer.data

    @staticmethod
    def test_download_url_field(
        api_request, filled_router, download_url_dataset, download_url_schema
    ):
        """ Prove that download url will contain correct identifier. """

        dossier_model = filled_router.all_models["download"]["dossiers"]
        dossier_model.objects.create(
            id=1,
            url=(
                "https://ngdsodev.blob.core.windows.net/"
                "quickstartb4e564a8-5071-4e41-9fc0-21a678f3815c/myblockblob"
            ),
        )
        DossiersSerializer = serializer_factory(dossier_model, 0, flat=False)

        api_request.dataset = download_url_schema

        dossiers_serializer = DossiersSerializer(
            dossier_model.objects.all(), context={"request": api_request}, many=True,
        )

        assert "sig=" in dossiers_serializer.data["dossiers"][0]["url"]
        assert "se=" in dossiers_serializer.data["dossiers"][0]["url"]
        assert "sv=" in dossiers_serializer.data["dossiers"][0]["url"]
        assert "sp=" in dossiers_serializer.data["dossiers"][0]["url"]
        assert "sr=b" in dossiers_serializer.data["dossiers"][0]["url"]
        assert "sp=r" in dossiers_serializer.data["dossiers"][0]["url"]


    def test_loose_relation_serialization(
        api_request, meldingen_schema, statistieken_model,
    ):
        """Prove that the serializer factory generates the right link
        for a loose relation field
        """

        class DummyView:
            def __init__(self, model):
                self.model = model

        api_request.dataset = meldingen_schema
        statistiek = statistieken_model.objects.create(id=1, buurt="03630000000078",)
        StatistiekenSerializer = serializer_factory(statistieken_model, 0)

        statistieken_serializer = StatistiekenSerializer(
            statistiek,
            context={"request": api_request, "view": DummyView(statistieken_model)},
        )

        assert (
            statistieken_serializer.data["buurt"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/"
        ), statistieken_serializer.data
