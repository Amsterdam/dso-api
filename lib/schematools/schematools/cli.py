import click

from schematools.schema.utils import schema_def_from_path, fetch_schema
from .ingest import create_tables, create_rows, fetch_rows, delete_tables

import django
from django.conf import settings
import dj_database_url

DATABASE_URL = "postgresql://postgres:postgres@localhost:5435/postgres"
# DATABASE_URL = os.getenv("DATABASE_URL")

settings.configure(
    DEBUG=True, DATABASES={"default": dj_database_url.parse(DATABASE_URL)}
)
django.setup()


@click.group()
def schema():
    pass


@schema.group()
def ingest():
    pass


@schema.group()
def delete():
    pass


@ingest.command()
@click.argument("schema_path")
def dataset(schema_path):
    dataset = fetch_schema(schema_def_from_path(schema_path))
    create_tables(dataset)
    # set_grants(schema, connection)


@ingest.command()
@click.argument("schema_path")
@click.argument("ndjson_path")
def records(schema_path, ndjson_path):
    # Add batching for rows.
    dataset = fetch_schema(schema_def_from_path(schema_path))
    srid = dataset["crs"].split(":")[-1]
    with open(ndjson_path) as fh:
        data = list(fetch_rows(fh, srid))
    create_rows(dataset, data)


@delete.command()
@click.argument("schema_path")
def _dataset(schema_path):
    dataset = fetch_schema(schema_def_from_path(schema_path))
    delete_tables(dataset)
