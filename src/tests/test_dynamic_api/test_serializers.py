from collections import OrderedDict
from datetime import date

import pytest

from dso_api.dynamic_api.serializers import serializer_factory
from rest_framework_dso.fields import EmbeddedField


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
        api_request, afval_cluster_model, afval_container_model, afval_cluster
    ):
        """Prove that the serializer factory properly generates the embedded fields.

        This checks whether the factory generates the proper FK/embedded fields.
        """
        afval_container = afval_container_model.objects.create(
            id=2,
            cluster=afval_cluster,
            serienummer="serie123",
            eigenaar_naam="datapunt",
            datum_creatie=date(2020, 2, 3),
        )

        # Generate serializers from models
        ContainerSerializer = serializer_factory(afval_container_model)
        # Important note is that ClusterSerializer is initiated as flat, not allowing relations to resolve.
        ClusterSerializer = serializer_factory(afval_cluster_model, flat=True)

        # Prove that EmbeddedField is created, as it should be.
        assert ContainerSerializer.Meta.embedded_fields == ["cluster"]
        assert isinstance(ContainerSerializer.cluster, EmbeddedField)
        assert ContainerSerializer.cluster.related_model is afval_cluster_model
        assert ContainerSerializer.cluster.serializer_class is ClusterSerializer

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        container_serializer = ContainerSerializer(
            afval_container, context={"request": api_request}
        )
        assert container_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/afvalwegingen/containers/2/",
                    "title": "(no title: Containers #2)",
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
    def test_expand(api_request, afval_container_model, afval_cluster):
        """Prove expanding works.

        The _embedded section is generated, using the cluster serializer.
        """
        ContainerSerializer = serializer_factory(afval_container_model)
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
                    "title": "(no title: Containers #2)",
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
                            "title": "(no title: Clusters #123.456)",
                        }
                    },
                    "id": "123.456",
                    "schema": "https://schemas.data.amsterdam.nl/datasets/afvalwegingen/afvalwegingen#clusters",  # noqa: E501
                    "status": "open",
                }
            },
        }

    @staticmethod
    def test_expand_none(api_request, afval_container_model):
        """Prove that expanding None values doesn't crash.

        The _embedded part has a None value instead.
        """
        ContainerSerializer = serializer_factory(afval_container_model)
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
                    "title": "(no title: Containers #3)",
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
    def test_expand_broken_relation(api_request, afval_container_model):
        """Prove that expanding non-existing FK values values doesn't crash.

        The _embedded part has a None value instead.
        """
        ContainerSerializer = serializer_factory(afval_container_model)
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
                    "title": "(no title: Containers #4)",
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
    def test_serializer_has_nested_table(
            api_request, parkeervakken_parkeervaak_model, parkeervakken_regime_model
    ):
        """Prove that the serializer factory properly generates nested tables.
        Serialiser should contain reverse relations.
        """
        parkeervaak = parkeervakken_parkeervaak_model.objects.create(
            id=1,
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
            buurtcode="A05d",
            parkeer_id="121138489047",
            straatnaam="Zoutkeetsgracht"
        )
        parkeervakken_regime_model.objects.create(
            id=1,
            parent=parkeervaak,
            bord="",
            dagen=[
                "ma",
                "di",
                "wo",
                "do",
                "vr",
                "za",
                "zo"
            ],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="69-SF-NT",
            opmerking="",
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None
        )

        ParkeervaakSerializer = serializer_factory(parkeervakken_parkeervaak_model)

        # Prove that no reverse relation to containers here.
        assert "regimes" in ParkeervaakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        parkeervaak_serializer = ParkeervaakSerializer(
            parkeervaak, context={"request": api_request}
        )
        assert parkeervaak_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/1/",
                    "title": "(no title: Parkeervakken #1)",
                }
            },
            "geom": None,
            "id": 1,
            "schema": "https://schemas.data.amsterdam.nl/datasets/parkeervakken/parkeervakken#parkeervakken",  # noqa: E501
            "type": "File",
            "soort": "MULDER",
            "aantal": 1.0,
            "eType": "E9",
            "buurtcode": "A05d",
            "parkeerId": "121138489047",
            "straatnaam": "Zoutkeetsgracht",
            "regimes": [
                OrderedDict(
                    bord='',
                    dagen=['ma',
                           'di',
                           'wo',
                           'do',
                           'vr',
                           'za',
                           'zo'],
                    soort='MULDER',
                    aantal=None,
                    eType='E6b',
                    kenteken='69-SF-NT',
                    eindTijd='23:59:00',
                    opmerking='',
                    beginTijd='00:00:00',
                    eindDatum=None,
                    beginDatum=None
                )
            ],
        }

    @staticmethod
    def test_flat_serializer_has_no_nested_table(
            api_request, parkeervakken_parkeervaak_model, parkeervakken_regime_model
    ):
        """Prove that the serializer factory properly skipping generation of reverse
        relations if `flat=True`.
        Flat serialiser should not contain any reverse relations,
        as flat serializers are used to represet instances of sub-serializers.
        """
        parkeervaak = parkeervakken_parkeervaak_model.objects.create(
            id=1,
            type="File",
            soort="MULDER",
            aantal=1.0,
            e_type="E9",
            buurtcode="A05d",
            parkeer_id="121138489047",
            straatnaam="Zoutkeetsgracht"
        )
        parkeervakken_regime_model.objects.create(
            id=1,
            parent=parkeervaak,
            bord="",
            dagen=[
                "ma",
                "di",
                "wo",
                "do",
                "vr",
                "za",
                "zo"
            ],
            soort="MULDER",
            aantal=None,
            e_type="E6b",
            kenteken="69-SF-NT",
            opmerking="",
            eind_tijd="23:59:00",
            begin_tijd="00:00:00",
            eind_datum=None,
            begin_datum=None
        )

        ParkeervaakSerializer = serializer_factory(parkeervakken_parkeervaak_model, flat=True)

        # Prove that no reverse relation to containers here.
        assert "regimes" not in ParkeervaakSerializer._declared_fields

        # Prove that data is serialized with relations.
        # Both the cluster_id field and 'cluster' field are generated.
        parkeervaak_serializer = ParkeervaakSerializer(
            parkeervaak, context={"request": api_request}
        )
        assert parkeervaak_serializer.data == {
            "_links": {
                "self": {
                    "href": "http://testserver/v1/parkeervakken/parkeervakken/1/",
                    "title": "(no title: Parkeervakken #1)",
                }
            },
            "geom": None,
            "id": 1,
            "schema": "https://schemas.data.amsterdam.nl/datasets/parkeervakken/parkeervakken#parkeervakken",  # noqa: E501
            "type": "File",
            "soort": "MULDER",
            "aantal": 1.0,
            "eType": "E9",
            "buurtcode": "A05d",
            "parkeerId": "121138489047",
            "straatnaam": "Zoutkeetsgracht"
        }
