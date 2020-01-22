import json
import requests
from . import types


def schema_def_from_path(schema_path):
    with open(schema_path) as fh:
        return json.load(fh)


def schema_defs_from_url(schemas_url):
    schema_lookup = {}
    response = requests.get(schemas_url)
    response.raise_for_status()
    for schema_dir_info in response.json():
        schema_dir_name = schema_dir_info["name"]
        response = requests.get(f"{schemas_url}{schema_dir_name}/")
        response.raise_for_status()
        for schema_file_info in response.json():
            schema_name = schema_file_info["name"]
            response = requests.get(f"{schemas_url}{schema_dir_name}/{schema_name}")
            response.raise_for_status()
            schema_lookup[schema_name] = response.json()
    return schema_lookup


def schema_def_from_url(schemas_url, schema_name):
    return schema_defs_from_url(schemas_url)[schema_name]


def fetch_schema(schema_def):
    return types.DatasetSchema(schema_def)
