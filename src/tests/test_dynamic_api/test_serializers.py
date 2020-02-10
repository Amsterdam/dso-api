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
    return afval_cluster_model.objects.create(id=1, status="open")


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
        ClusterSerializer = serializer_factory(afval_cluster_model)

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
            "schema": "",
            "cluster_id": 1,
            "cluster": "http://testserver/v1/afvalwegingen/clusters/1/",
            "serienummer": "serie123",
            "datum_creatie": "2020-02-03",
            "datum_leegmaken": None,
            "eigenaar_naam": "datapunt",
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
            "schema": "",
            "cluster_id": 1,
            "cluster": "http://testserver/v1/afvalwegingen/clusters/1/",
            "serienummer": None,
            "datum_creatie": None,
            "datum_leegmaken": None,
            "eigenaar_naam": None,
            "_embedded": {
                "cluster": {
                    "_links": {
                        "self": {
                            "href": "http://testserver/v1/afvalwegingen/clusters/1/",
                            "title": "(no title: Clusters #1)",
                        }
                    },
                    "id": 1,
                    "schema": "",
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
            "schema": "",
            "cluster_id": None,
            "cluster": None,
            "serienummer": None,
            "datum_creatie": None,
            "datum_leegmaken": None,
            "eigenaar_naam": None,
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
            "schema": "",
            "cluster_id": 99,
            "cluster": "http://testserver/v1/afvalwegingen/clusters/99/",
            "serienummer": None,
            "datum_creatie": None,
            "datum_leegmaken": None,
            "eigenaar_naam": None,
            "_embedded": {"cluster": None},
        }
