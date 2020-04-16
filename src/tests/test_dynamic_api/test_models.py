from django.contrib.gis.db import models
from django_postgres_unlimited_varchar import UnlimitedCharField
from schematools.contrib.django.models import model_factory, schema_models_factory


def test_model_factory_fields(afval_schema):
    """Prove that the fields from the schema will be generated"""
    table = afval_schema.tables[0]
    model_cls = model_factory(table, base_app_name="dso_api.dynamic_api")
    meta = model_cls._meta
    assert set(f.name for f in meta.get_fields()) == {
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
    assert meta.app_label == afval_schema.id

    table_with_id_as_string = afval_schema.tables[1]
    model_cls = model_factory(table_with_id_as_string, base_app_name="dso_api.dynamic_api")
    meta = model_cls._meta
    assert meta.get_field("id").primary_key
    assert isinstance(meta.get_field("id"), UnlimitedCharField)


def test_model_factory_relations(afval_schema):
    """Prove that relations between models can be resolved"""
    models = {cls._meta.model_name: cls for cls in schema_models_factory(
        afval_schema, base_app_name="dso_api.dynamic_api")}
    cluster_fk = models["containers"]._meta.get_field("cluster")
    # Cannot compare using identity for dynamically generated classes
    assert (
        cluster_fk.related_model._table_schema.id == models["clusters"]._table_schema.id
    )
