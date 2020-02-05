from django.contrib.gis.db import models
from django_postgres_unlimited_varchar import UnlimitedCharField
from dso_api.lib.schematools.models import model_factory, schema_models_factory


def test_model_factory_fields(afval_schema):
    """Prove that the fields from the schema will be generated"""
    table = afval_schema.tables[0]
    model_cls = model_factory(table)
    meta = model_cls._meta
    assert len(meta.get_fields()) == len(table["schema"]["properties"])
    assert meta.get_field("id").primary_key
    assert isinstance(meta.get_field("cluster_id"), models.ForeignKey)
    assert isinstance(meta.get_field("eigenaar_naam"), UnlimitedCharField)
    assert isinstance(meta.get_field("datum_creatie"), models.DateField)
    assert isinstance(meta.get_field("datum_leegmaken"), models.DateTimeField)
    assert meta.app_label == afval_schema.id


def test_model_factory_relations(afval_schema):
    """Prove that relations between models can be resolved"""
    models = {cls._meta.model_name: cls for cls in schema_models_factory(afval_schema)}

    cluster_fk = models["containers"]._meta.get_field("cluster")
    assert cluster_fk.related_model is models["clusters"]
