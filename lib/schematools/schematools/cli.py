import click

from schematools.schema.utils import schema_def_from_path, fetch_schema
from .db import create_tables, create_rows, fetch_rows, delete_tables

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
def create():
    pass


@schema.group()
def delete():
    pass


@create.command()
@click.argument("schema_path")
@click.option("--table", "-t", multiple=True, help="Specify subset of the tables")
def dataset(schema_path, table):
    dataset = fetch_schema(schema_def_from_path(schema_path))
    create_tables(dataset)
    # set_grants(schema, connection)


@create.command()
@click.argument("schema_path")
@click.argument("ndjson_path")
def records(schema_path, ndjson_path):
    # XXX Add batching for rows (streaming)
    dataset = fetch_schema(schema_def_from_path(schema_path))
    srid = dataset["crs"].split(":")[-1]
    with open(ndjson_path) as fh:
        data = list(fetch_rows(fh, srid))
    create_rows(dataset, data)


@delete.command("dataset")
@click.argument("schema_path")
@click.option("--table", "-t", multiple=True, help="Specify subset of the tables")
def _dataset(schema_path, table):
    dataset = fetch_schema(schema_def_from_path(schema_path))
    delete_tables(dataset)
