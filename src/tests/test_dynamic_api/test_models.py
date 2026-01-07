import pytest
from django.contrib.gis.db import models
from schematools.contrib.django.factories import DjangoModelFactory


@pytest.mark.django_db
def test_model_factory_fields(afval_dataset):
    """Prove that the fields from the schema will be generated"""
    factory = DjangoModelFactory(afval_dataset)
    table = afval_dataset.schema.tables[0]
    model_cls = factory.build_model(table)
    meta = model_cls._meta
    assert {f.name for f in meta.get_fields()} == {
        "id",
        "cluster",
        "serienummer",
        "eigenaar_naam",
        "datum_creatie",
        "datum_leegmaken",
        "geometry",
    }
    assert meta.get_field("id").primary_key
    assert isinstance(meta.get_field("cluster_id"), models.ForeignKey)
    assert isinstance(meta.get_field("eigenaar_naam"), models.CharField)
    assert isinstance(meta.get_field("datum_creatie"), models.DateField)
    assert isinstance(meta.get_field("datum_leegmaken"), models.DateTimeField)
    geo_field = meta.get_field("geometry")
    assert geo_field.srid == 28992
    assert geo_field.db_index
    assert meta.app_label == f"{afval_dataset.schema.id}_v1"

    table_with_id_as_string = afval_dataset.schema.tables[1]
    model_cls = factory.build_model(table_with_id_as_string)
    meta = model_cls._meta
    assert meta.get_field("id").primary_key
    assert isinstance(meta.get_field("id"), models.CharField)


@pytest.mark.django_db
def test_model_factory_relations(afval_dataset):
    """Prove that relations between models can be resolved"""
    factory = DjangoModelFactory(afval_dataset)
    models = {cls._meta.model_name: cls for cls in factory.build_models()}
    cluster_fk = models["containers"]._meta.get_field("cluster")
    # Cannot compare using identity for dynamically generated classes
    assert cluster_fk.related_model._table_schema.id == models["clusters"]._table_schema.id


@pytest.mark.django_db
def test_sealed_model_can_refresh_fields(afval_container):
    # should not raise
    afval_container.refresh_from_db(fields=["serienummer", "geometry"])


@pytest.mark.django_db
def test_sealed_model_raises_on_unavailable_fields(afval_container):
    with pytest.raises(RuntimeError, match="Deferred attribute access"):
        afval_container.refresh_from_db(fields=["non_existing_field"])
