from datetime import date

import pytest

from dso_api.dynamic_api.serializers import serializer_factory
from rest_framework_dso.fields import EmbeddedField


@pytest.fixture(autouse=True)
def clear_caches():
    yield  # run tests first
    serializer_factory.cache_clear()


@pytest.fixture()
def afval_cluster(filled_router):
    Cluster = filled_router.all_models["afvalwegingen"]["clusters"]
    return Cluster.objects.create(id=1, status="open")


@pytest.mark.django_db
def test_serializer_factory_relations(api_rf, filled_router, afval_cluster):
    """Prove that the serializer factory properly generates the embedded fields"""
    # Get dynamically generated models
    Cluster = filled_router.all_models["afvalwegingen"]["clusters"]
    Container = filled_router.all_models["afvalwegingen"]["containers"]
    afval_container = Container.objects.create(
        id=2,
        cluster=afval_cluster,
        serienummer="serie123",
        eigenaar_naam="datapunt",
        datum_creatie=date(2020, 2, 3),
    )

    # Generate serializers from models
    ContainerSerializer = serializer_factory(Container)
    ClusterSerializer = serializer_factory(Cluster)

    # Prove that EmbeddedField is created, as it should be.
    assert ContainerSerializer.Meta.embedded_fields == ["cluster"]
    assert isinstance(ContainerSerializer.cluster, EmbeddedField)
    assert ContainerSerializer.cluster.related_model is Cluster
    assert ContainerSerializer.cluster.serializer_class is ClusterSerializer

    # Prove that data is serialized with relations.
    # Both the cluster_id field and 'cluster' field are generated.
    request = api_rf.get("/")
    container_serializer = ContainerSerializer(
        afval_container, context={"request": request}
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
        "eigenaar_naam": "datapunt",
    }

    # Prove that expands work on object-detail level
    container_serializer = ContainerSerializer(
        afval_container, context={"request": request}, fields_to_expand=["cluster"]
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
        "eigenaar_naam": "datapunt",
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

    # Prove that expanding None values doesn't crash
    container_without_cluster = Container.objects.create(
        id=3,
        cluster=None,
        serienummer="serie123",
        eigenaar_naam="datapunt",
        datum_creatie=date(2020, 2, 3),
    )
    container_serializer = ContainerSerializer(
        container_without_cluster,
        context={"request": request},
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
        "serienummer": "serie123",
        "datum_creatie": "2020-02-03",
        "eigenaar_naam": "datapunt",
        "_embedded": {"cluster": None},
    }
