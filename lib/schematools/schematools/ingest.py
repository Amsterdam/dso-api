import ndjson
from shapely.geometry import shape
from django.db import connection

from .db import fetch_models_from_schema


def fetch_rows(fh, srid):
    data = ndjson.load(fh)
    for row in data:
        row["geometry"] = f"SRID={srid};{shape(row['geometry']).wkt}"
        yield row


def create_tables(dataset, tables=None):

    for model in fetch_models_from_schema(dataset):
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(model)


def delete_tables(dataset, tables=None):

    for model in fetch_models_from_schema(dataset):
        with connection.schema_editor() as schema_editor:
            # XXX Not sure if the works with relation, maybe need to revert to raw sql + cascade
            schema_editor.delete_model(model)


def create_rows(dataset, data):
    model_lookup = {
        model._meta.db_table: model for model in fetch_models_from_schema(dataset)
    }
    for row in data:
        dataset_name, table_name = row["schema"].split("/")[-2:]
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
