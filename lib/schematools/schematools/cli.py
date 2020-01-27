import click
import django
import environ
from django.conf import settings

from .schema.types import DatasetSchema

settings.configure(
    DATABASES={"default": environ.Env().db_url("DATABASE_URL")},
    DEBUG=True,
)
django.setup()

# Late import because Django must be configured first
from .db import create_rows, create_tables, delete_tables, fetch_rows  # noqa


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
    dataset = DatasetSchema.from_file(schema_path)
    create_tables(dataset, tables=table or None)
    # set_grants(schema, connection)


@create.command()
@click.argument("schema_path")
@click.argument("ndjson_path")
def records(schema_path, ndjson_path):
    # XXX Add batching for rows (streaming)
    dataset = DatasetSchema.from_file(schema_path)
    srid = dataset["crs"].split(":")[-1]
    with open(ndjson_path) as fh:
        data = list(fetch_rows(fh, srid))
    create_rows(dataset, data)


@delete.command("dataset")
@click.argument("schema_path")
@click.option("--table", "-t", multiple=True, help="Specify subset of the tables")
def _dataset(schema_path, table):
    dataset = DatasetSchema.from_file(schema_path)
    delete_tables(dataset, tables=table or None)
