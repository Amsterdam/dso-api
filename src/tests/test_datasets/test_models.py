import pytest

from schematools.contrib.django.models import Dataset


def test_save_blocks_invalid_json():
    """Prove that invalid JSON won't be stored in the database."""
    dataset = Dataset(name="foobar", schema_data="NOT_JSON")
    with pytest.raises(RuntimeError):
        dataset.save()


@pytest.mark.django_db
def test_save_empty_schema(bommen_schema_json, django_assert_num_queries):
    """Prove that the dataset table models are created on save."""
    dataset = Dataset(name="empty", schema_data="")

    with django_assert_num_queries(1):
        dataset.save()
    assert dataset.tables.count() == 0


@pytest.mark.django_db
def test_save_schema_tables_add(bommen_schema_json):
    """Prove that the dataset table models are created on save."""
    dataset = Dataset(name="testing", schema_data=bommen_schema_json)
    dataset.save()
    assert dataset.tables.count() == 1, dataset.tables.all()
    table = dataset.tables.get()
    assert table.name == "bommen"
    assert table.db_table == "bommen_bommen"
    assert table.enable_geosearch is True


@pytest.mark.django_db
def test_save_schema_tables_with_disabled_geosearch(settings, bommen_schema_json):
    """Prove that the dataset table models are created with geosearch disabled
    if dataset.name in settings.AMSTERDAM_SCHEMA['geosearch_disabled_datasets]."""
    settings.AMSTERDAM_SCHEMA["geosearch_disabled_datasets"] = ["testing"]
    dataset = Dataset(name="testing", schema_data=bommen_schema_json)
    dataset.save()
    assert dataset.tables.count() == 1, dataset.tables.all()
    table = dataset.tables.get()
    assert table.name == "bommen"
    assert table.db_table == "bommen_bommen"
    assert table.enable_geosearch is False


@pytest.mark.django_db
def test_save_schema_tables_with_geometry_type(bommen_schema_json):
    """Prove that the dataset table models are created with geosearch field type set to schema."""
    bommen_schema_json["tables"][0]["schema"]["properties"]["geometry"][
        "$ref"
    ] = "https://geojson.org/schema/Point.json"
    dataset = Dataset(name="testing", schema_data=bommen_schema_json)
    dataset.save()
    assert dataset.tables.count() == 1, dataset.tables.all()
    table = dataset.tables.get()
    assert table.name == "bommen"
    assert table.db_table == "bommen_bommen"
    assert table.geometry_field == "geometry"
    assert table.geometry_field_type == "Point"


@pytest.mark.django_db
def test_save_schema_tables_delete(bommen_schema_json):
    """Prove that the dataset table models are created on save."""
    dataset = Dataset(name="bommen", schema_data=bommen_schema_json)
    dataset.save()
    assert dataset.tables.count() == 1

    dataset.schema_data = {
        "id": "bommen",
        "type": "dataset",
        "title": "",
        "version": "0.0.1",
        "crs": "EPSG:28992",
        "tables": [],  # removed tables
    }
    dataset.save()
    assert dataset.tables.count() == 0
