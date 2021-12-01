from pathlib import Path

import pytest
from schematools.permissions import UserScopes
from schematools.utils import dataset_schema_from_path

from dso_api.dynamic_api.permissions import _filter_ok

SCHEMA = dataset_schema_from_path(Path(__file__).parent.parent / "files" / "relationauth.json")


@pytest.mark.parametrize(
    ["field_name", "scopes", "expect"],
    [
        ("name", "REFERS REFERS/NAME", True),
        ("base", "REFERS REFERS/NAME", False),
        ("base", "REFERS REFERS/BASE", False),
        ("base", "REFERS REFERS/BASE BASE", False),
        ("base", "REFERS REFERS/BASE BASE/ID", False),
        ("base", "REFERS BASE BASE/ID", False),
        ("base", "REFERS/BASE BASE BASE/ID", False),
        ("base", "REFERS REFERS/BASE BASE BASE/ID", True),
    ],
)
def test_filter_ok(field_name: str, scopes: str, expect: bool):
    schema = SCHEMA.get_table_by_id("refers")

    scopes = UserScopes(query_params={}, request_scopes=scopes.split())
    assert _filter_ok(field_name, scopes, schema) == expect
