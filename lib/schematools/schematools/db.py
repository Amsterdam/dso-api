from __future__ import annotations

import ndjson
from schematools.schema.types import DatasetSchema
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon
from django.db import connection

from .models import schema_models_factory


def fetch_rows(fh, srid):
    """ Need to convert Polygon to MultiPolygon, some inputs have mixed geo types """
    data = ndjson.load(fh)
    for row in data:
        s = shape(row["geometry"])
        if isinstance(s, Polygon):
            s = MultiPolygon([s])
        row["geometry"] = f"SRID={srid};{s.wkt}"
        yield row


def create_tables(dataset: DatasetSchema, tables=None):
    with connection.schema_editor() as schema_editor:
        for model in schema_models_factory(dataset, tables=tables):
            schema_editor.create_model(model)


def delete_tables(dataset: DatasetSchema, tables=None):
    with connection.schema_editor() as schema_editor:
        for model in schema_models_factory(dataset, tables=tables):
            # XXX Not sure if the works with relation, maybe need to revert to raw sql + cascade
            schema_editor.delete_model(model)


def create_rows(dataset, data):
    model_lookup = {
        model._meta.db_table: model for model in schema_models_factory(dataset)
    }
    for row in data:
        dataset_name, table_name = row["schema"].rsplit("/", 2)[-2:]
        field_names = set(
            dataset.get_table_by_id(table_name)["schema"]["properties"].keys()
        )
        db_table = f"{dataset_name}_{table_name}"
        model_lookup[db_table].objects.create(
            **{k.lower(): v for k, v in row.items() if k in field_names}
        )


def set_grants(dataset):
    cursor = connection.cursor()
    # for table in dataset.tables:
    # cursor.execute(f"GRANT SELECT ON {dataset.id}_{table.id} TO PUBLIC")
