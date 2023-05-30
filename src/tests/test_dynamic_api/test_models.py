import pytest
from django.contrib.gis.db import models
from schematools.contrib.django.factories import model_factory, schema_models_factory
from schematools.contrib.django.fields import UnlimitedCharField


@pytest.mark.django_db
def test_model_factory_fields(afval_dataset):
    """Prove that the fields from the schema will be generated"""
    table = afval_dataset.schema.tables[0]
    model_cls = model_factory(afval_dataset, table, base_app_name="dso_api.dynamic_api")
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
    assert isinstance(meta.get_field("eigenaar_naam"), UnlimitedCharField)
    assert isinstance(meta.get_field("datum_creatie"), models.DateField)
    assert isinstance(meta.get_field("datum_leegmaken"), models.DateTimeField)
    geo_field = meta.get_field("geometry")
    assert geo_field.srid == 28992
    assert geo_field.db_index
    assert meta.app_label == afval_dataset.schema.id

    table_with_id_as_string = afval_dataset.schema.tables[1]
    model_cls = model_factory(
        afval_dataset, table_with_id_as_string, base_app_name="dso_api.dynamic_api"
    )
    meta = model_cls._meta
    assert meta.get_field("id").primary_key
    assert isinstance(meta.get_field("id"), UnlimitedCharField)


@pytest.mark.django_db
def test_model_factory_relations(afval_dataset):
    """Prove that relations between models can be resolved"""
    models = {
        cls._meta.model_name: cls
        for cls in schema_models_factory(afval_dataset, base_app_name="dso_api.dynamic_api")
    }
    cluster_fk = models["containers"]._meta.get_field("cluster")
    # Cannot compare using identity for dynamically generated classes
    assert cluster_fk.related_model._table_schema.id == models["clusters"]._table_schema.id
