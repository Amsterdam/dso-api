from datetime import date

import pytest
from django.apps import apps
from django.core.validators import EmailValidator, URLValidator
from schematools.permissions import UserScopes
from schematools.types import ProfileSchema

from dso_api.dynamic_api.serializers import serializer_factory, serializer_factory_cache
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.views import DSOViewMixin
from tests.utils import (
    api_request_with_scopes,
    normalize_data,
    patch_field_auth,
    to_drf_request,
    unlazy,
)


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    serializer_factory_cache.clear()


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
        drf_request,
        afval_schema,
        afval_cluster_model,
        afval_container_model,
        afval_cluster,
        filled_router,
    ):
        """Prove that the serializer factory properly generates the embedded fields.

        This checks whether the factory generates the proper FK/embedded fields.
        """
        # Access real models to perform 'is' test below.
        afval_cluster_model = unlazy(afval_cluster_model)
        afval_container_model = unlazy(afval_container_model)

        # Confirm that the model is the object that Django also has registered
        # (if this differs, create_tables() might be called twice).
        assert afval_cluster_model is apps.get_model("afvalwegingen.clusters")
        assert afval_container_model is apps.get_model("afvalwegingen.containers")

        drf_request.dataset = afval_schema
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
        assert ContainerSerializer.Meta.embedded_fields == ["cluster"]
        assert isinstance(ContainerSerializer.cluster, EmbeddedField)

        # Prove that the EmbeddedField references the proper models and serializers.
        # This also tests whether there aren't any old references left.
        assert ContainerSerializer.cluster.related_model is afval_cluster_model, (
            "Old Django models were still referenced: "
            f"id {id(ContainerSerializer.cluster.related_model)} vs "
            f"id {id(afval_cluster_model)} "
            f"(creation counter {ContainerSerializer.cluster.related_model.CREATION_COUNTER}"
            f" vs {afval_cluster_model.CREATION_COUNTER})",
        )
        assert ContainerSerializer.cluster.serializer_class.__name__ == ClusterSerializer.__name__

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        container_serializer = ContainerSerializer(
            afval_container, context={"request": drf_request}
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                    "title": "123.456",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "2",
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
    def test_expand(afval_schema, afval_container_model, afval_cluster):
        """Prove expanding works.

        The _embedded section is generated, using the cluster serializer.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        drf_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model)
        afval_container = afval_container_model.objects.create(id=2, cluster=afval_cluster)

        # Prove that expands work on object-detail level
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "2",
                },
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                    "title": "123.456",
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
                            "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                            "title": "123.456",
                        },
                        "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#clusters",  # noqa: E501
                    },
                    "id": "123.456",
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_expand_none(afval_schema, afval_container_model):
        """Prove that expanding None values doesn't crash.

        The _embedded part has a None value instead.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        drf_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model)
        container_without_cluster = afval_container_model.objects.create(
            id=3,
            cluster=None,
        )
        container_serializer = ContainerSerializer(
            container_without_cluster,
            context={"request": drf_request},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/3/",
                    "title": "3",
                },
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
    def test_expand_broken_relation(afval_schema, afval_container_model):
        """Prove that expanding non-existing FK values values doesn't crash.
           Cluster will not be expanded to a url, because the pk_only_optimization
           has been switched off for hyperlinked related fields.
        The _embedded part has a None value instead.
        """
        drf_request = to_drf_request(api_request_with_scopes(["BAG/R"]))
        drf_request.dataset = afval_schema
        ContainerSerializer = serializer_factory(afval_container_model)
        container_invalid_cluster = afval_container_model.objects.create(
            id=4,
            cluster_id=99,
        )
        container_serializer = ContainerSerializer(
            container_invalid_cluster,
            context={"request": drf_request},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/4/",
                    "title": "4",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/dataset#containers",  # noqa: E501
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
        drf_request.dataset = afval_dataset.schema
        ContainerSerializer = serializer_factory(afval_container_model, 0)
        afval_container = afval_container_model.objects.create(id=2, cluster=afval_cluster)

        # Prove that expands work on object-detail level
        container_serializer = ContainerSerializer(
            afval_container,
            context={"request": drf_request},
            fields_to_expand=["cluster"],
        )
        data = normalize_data(container_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/test/afvalwegingen/dataset#containers",  # noqa: E501
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "2",
                },
                "cluster": {
                    "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                    "title": "123.456",
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
                            "href": "http://testserver/v1/afvalwegingen/clusters/123.456/",
                            "title": "123.456",
                        },
                        "schema": "https://schemas.data.amsterdam.nl/datasets/test/afvalwegingen/dataset#clusters",  # noqa: E501
                    },
                    "id": "123.456",
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_backwards_relation(
        drf_request,
        gebieden_schema,
        gebieden_models,
    ):
        """Show backwards"""
        drf_request.dataset = gebieden_schema
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
            context={"request": drf_request},
        )
        data = normalize_data(stadsdelen_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/gebieden/stadsdelen/0363/?volgnummer=1",
                    "title": "0363.1",
                    "volgnummer": 1,
                    "identificatie": "0363",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/dataset#stadsdelen",  # NoQA
                "wijk": [
                    {
                        "href": "http://testserver/v1/gebieden/wijken/03630000000001/?volgnummer=1",  # NoQA
                        "title": "03630000000001.1",
                        "volgnummer": 1,
                        "identificatie": "03630000000001",
                    }
                ],
            },
            "id": "0363.1",
            "naam": "Stadsdeel",
            "code": None,
            "eindGeldigheid": None,
            "beginGeldigheid": None,
            "registratiedatum": None,
            "documentdatum": None,
            "documentnummer": None,
            "geometrie": None,
        }

    @staticmethod
    def test_multiple_backwards_relations(
        drf_request,
        vestiging_schema,
        vestiging_adres_model,
        vestiging_vestiging_model,
        vestiging1,
        vestiging2,
        post_adres1,
    ):
        """Show backwards"""
        drf_request.dataset = vestiging_schema

        VestigingSerializer = serializer_factory(vestiging_vestiging_model)

        vestiging_serializer = VestigingSerializer(
            vestiging1,
            context={"request": drf_request},
        )
        data = normalize_data(vestiging_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/1/",
                    "title": "1",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#vestiging",  # noqa: E501
                "postAdres": {
                    "href": "http://testserver/v1/vestiging/adres/3/",
                    "title": "3",
                },
                "bezoekAdres": {
                    "href": "http://testserver/v1/vestiging/adres/1/",
                    "title": "1",
                },
            },
            "id": 1,
            "naam": "Snake Oil",
            "postAdresId": 3,
            "bezoekAdresId": 1,
        }

        vestiging_serializer = VestigingSerializer(
            vestiging2,
            context={"request": drf_request},
        )
        data = normalize_data(vestiging_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/vestiging/vestiging/2/",
                    "title": "2",
                },
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#vestiging",  # noqa: E501
                "postAdres": {
                    "href": "http://testserver/v1/vestiging/adres/3/",
                    "title": "3",
                },
                "bezoekAdres": {
                    "href": "http://testserver/v1/vestiging/adres/2/",
                    "title": "2",
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
            context={"request": drf_request},
        )
        data = normalize_data(adres_serializer.data)
        assert data == {
            "_links": {
                "schema": "https://schemas.data.amsterdam.nl/datasets/vestiging/dataset#adres",
                "self": {
                    "href": "http://testserver/v1/vestiging/adres/3/",
                    "title": "3",
                },
                "vestigingenPost": [
                    {
                        "href": "http://testserver/v1/vestiging/vestiging/1/",
                        "title": "1",
                    },
                    {
                        "href": "http://testserver/v1/vestiging/vestiging/2/",
                        "title": "2",
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
        drf_request,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        drf_request.dataset = parkeervakken_schema
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

        ParkeervakSerializer = serializer_factory(parkeervakken_parkeervak_model)

        # Prove that no reverse relation to containers here.
        assert "regimes" in ParkeervakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.

        parkeervak_serializer = ParkeervakSerializer(parkeervak, context={"request": drf_request})
        data = normalize_data(parkeervak_serializer.data)
        assert data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/121138489047/",
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
            "regimes": [
                {
                    "bord": "",
                    "dagen": ["ma", "di", "wo", "do", "vr", "za", "zo"],
                    "soort": "MULDER",
                    "aantal": None,
                    "eType": "E6b",
                    "kenteken": "69-SF-NT",
                    "eindTijd": "23:59:00",
                    "opmerking": "",
                    "beginTijd": "00:00:00",
                    "eindDatum": None,
                    "beginDatum": None,
                }
            ],
        }

    @staticmethod
    def test_flat_serializer_has_no_nested_table(
        drf_request,
        parkeervakken_schema,
        parkeervakken_parkeervak_model,
        parkeervakken_regime_model,
    ):
        """Prove that the serializer factory properly skipping generation of reverse
        relations if `flat=True`.
        Flat serialiser should not contain any reverse relations,
        as flat serializers are used to represet instances of sub-serializers.
        """
        drf_request.dataset = parkeervakken_schema
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

        ParkeervakSerializer = serializer_factory(parkeervakken_parkeervak_model, flat=True)

        # Prove that no reverse relation to containers here.
        assert "regimes" not in ParkeervakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.

        parkeervak_serializer = ParkeervakSerializer(parkeervak, context={"request": drf_request})
        data = normalize_data(parkeervak_serializer.data)
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/parkeervakken/parkeervakken/121138489047/"},
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
        }

    @staticmethod
    def test_display_title_present(
        drf_request,
        fietspaaltjes_schema,
        fietspaaltjes_model,
        fietspaaltjes_data,
    ):
        """ Prove that title element shows display value if display field is specified """

        FietsplaatjesSerializer = serializer_factory(fietspaaltjes_model)

        drf_request.dataset = fietspaaltjes_schema

        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data, context={"request": drf_request}
        )

        assert "'title': 'reference for DISPLAY FIELD'" in str(fietsplaatjes_serializer.data)

    @staticmethod
    def test_no_display_title_present(
        drf_request,
        fietspaaltjes_schema_no_display,
        fietspaaltjes_model_no_display,
        fietspaaltjes_data_no_display,
    ):
        """ Prove that title element is omitted if display field is not specified """

        FietsplaatjesSerializer = serializer_factory(fietspaaltjes_model_no_display, flat=True)

        drf_request.dataset = fietspaaltjes_schema_no_display

        fietsplaatjes_serializer = FietsplaatjesSerializer(
            fietspaaltjes_data_no_display, context={"request": drf_request}
        )

        assert "'title': 'reference for DISPLAY FIELD'" not in str(fietsplaatjes_serializer.data)

    @staticmethod
    def test_uri_field_present(explosieven_model):
        """ Prove that a URLfield is stored as a charfield and default 200 in length """
        assert explosieven_model._meta.get_field("pdf").get_internal_type() == "CharField"
        assert explosieven_model._meta.get_field("pdf").max_length == 200

    @staticmethod
    def test_uri_field_can_validate(
        drf_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a URLfield can be validated by the URIValidator """

        ExplosievenSerializer = serializer_factory(explosieven_model, flat=True)

        drf_request.dataset = explosieven_schema

        validate_uri = URLValidator()

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": drf_request}
        )

        # Validation passes if outcome is None
        assert validate_uri(explosieven_serializer.data["pdf"]) is None

    @staticmethod
    def test_uri_field_is_URL_encoded(
        drf_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a URLfield content is URL encoded i.e. space to %20 """

        ExplosievenSerializer = serializer_factory(explosieven_model, flat=True)

        drf_request.dataset = explosieven_schema

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": drf_request}
        )

        # Validation passes if a space does not exists (translated to %20)
        assert " " not in str(explosieven_serializer.data["pdf"]) and "%20" in str(
            explosieven_serializer.data["pdf"]
        )

    @staticmethod
    def test_email_field_can_validate_with_validator(
        drf_request, explosieven_schema, explosieven_model, explosieven_data
    ):
        """ Prove that a EmailField can be validated by the EmailValidator """

        ExplosievenSerializer = serializer_factory(explosieven_model, flat=True)

        drf_request.dataset = explosieven_schema

        validate_email = EmailValidator()

        explosieven_serializer = ExplosievenSerializer(
            explosieven_data, context={"request": drf_request}
        )

        # Validation passes if outcome is None
        assert validate_email(explosieven_serializer.data["emailadres"]) is None

    @staticmethod
    def test_indirect_self_reference(ligplaatsen_model, filled_router):
        """Prove that a dataset with two tables that
        are mutually related generates a serialize without any problems
        (no infinite recursion)
        """
        serializer_factory(ligplaatsen_model)

    @staticmethod
    def test_field_permissions_display_first_letter(
        drf_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """ Prove that only first letter is seen in Profile allows only it."""
        # does not have scope for Dataset or Table
        drf_request.dataset = fietspaaltjes_schema
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
            fietspaaltjes_data, context={"request": drf_request}
        )

        assert fietspaaltjes_serializer.data["area"] == "A"

    @staticmethod
    def test_field_permissions_display_first_letter_many(
        drf_request, fietspaaltjes_schema, fietspaaltjes_model, fietspaaltjes_data
    ):
        """ Prove that only first letter is seen in Profile allows only it in listing. """
        drf_request.dataset = fietspaaltjes_schema
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
            context={"request": drf_request},
            many=True,
        )

        fietspaaltjes = list(fietspaaltjes_serializer.data["fietspaaltjes"])  # consume generator
        assert fietspaaltjes[0]["area"] == "A", fietspaaltjes_serializer.data

    @staticmethod
    def test_download_url_field(
        drf_request, download_url_dataset, download_url_schema, filled_router
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
        DossiersSerializer = serializer_factory(dossier_model)

        drf_request.dataset = download_url_schema

        dossiers_serializer = DossiersSerializer(
            dossier_model.objects.all(),
            context={"request": drf_request},
            many=True,
        )

        dossiers = list(dossiers_serializer.data["dossiers"])  # consume generator
        url = dossiers[0]["url"]
        assert "sig=" in url
        assert "se=" in url
        assert "sv=" in url
        assert "sp=" in url
        assert "sr=b" in url
        assert "sp=r" in url

    @staticmethod
    def test_download_url_field_empty_field(
        drf_request, download_url_dataset, download_url_schema, filled_router
    ):
        """ Prove that empty download url not crashing api. """

        dossier_model = filled_router.all_models["download"]["dossiers"]
        dossier_model.objects.create(
            id=1,
            url="",
        )
        DossiersSerializer = serializer_factory(dossier_model)

        drf_request.dataset = download_url_schema

        dossiers_serializer = DossiersSerializer(
            dossier_model.objects.all(),
            context={"request": drf_request},
            many=True,
        )

        dossiers = list(dossiers_serializer.data["dossiers"])  # consume generator
        assert dossiers[0]["url"] == ""

    @staticmethod
    def test_loose_relation_serialization(
        drf_request,
        meldingen_schema,
        statistieken_model,
    ):
        """Prove that the serializer factory generates the right link
        for a loose relation field
        """

        class DummyView(DSOViewMixin):
            def __init__(self, model):
                self.model = model

        drf_request.dataset = meldingen_schema
        statistiek = statistieken_model.objects.create(
            id=1,
            buurt="03630000000078",
        )
        StatistiekenSerializer = serializer_factory(statistieken_model)

        statistieken_serializer = StatistiekenSerializer(
            statistiek,
            context={"request": drf_request, "view": DummyView(statistieken_model)},
        )

        assert (
            statistieken_serializer.data["_links"]["buurt"]["href"]
            == "http://testserver/v1/gebieden/buurten/03630000000078/"
        ), statistieken_serializer.data
