from __future__ import annotations

from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from schematools.permissions import UserScopes
from schematools.utils import dataset_schema_from_path

from dso_api.dynamic_api.filters import parser

SCHEMA_SIMPLE = dataset_schema_from_path(
    Path(__file__).parent.parent / "files" / "relationauth.json"
)
SCHEMA_COMPOSITE = dataset_schema_from_path(
    Path(__file__).parent.parent / "files" / "relationauthcomposite.json"
)


@pytest.mark.parametrize(
    ["field_name", "scopes", "exc_type"],
    [
        ("", "", ValidationError),
        # Filtering on a relation requires scopes for both the relation and the base table.
        ("baseId", "REFERS REFERS/BASE BASE BASE/TABLE", None),
        ("base", "REFERS REFERS/BASE BASE BASE/TABLE", None),  # uses id internally
        # This one doesn't look at the relation field.
        ("name", "REFERS REFERS/NAME", None),
        # These look at the relation field without access to the base table.
        # REFERS/BASE opens the relation, but not the base table.
        ("baseId", "REFERS REFERS/NAME", PermissionDenied),
        ("baseId", "REFERS REFERS/BASE", PermissionDenied),
        ("base", "REFERS REFERS/BASE BASE", PermissionDenied),
    ],
)
def test_check_filter_simple(field_name: str, scopes: str, exc_type: type[Exception] | None):
    """Test filter auth/validation with a simple-key relation."""
    table_schema = SCHEMA_SIMPLE.get_table_by_id("refers")

    scopes = UserScopes(query_params={}, request_scopes=scopes.split())
    if exc_type is None:
        assert parser.QueryFilterEngine.to_orm_path(field_name, table_schema, scopes)
    else:
        with pytest.raises(exc_type):
            parser.QueryFilterEngine.to_orm_path(field_name, table_schema, scopes)


@pytest.mark.parametrize(
    ["field_name", "scopes", "exc_type"],
    [
        # Loose relation syntax. TODO: get rid of this.
        ("baseId", "REFERS REFERS/BASE BASE BASE/TABLE", None),
        # Reference to relation field, e.g., base.id=$id&base.volgnr=$volgnr
        ("base.id", "REFERS REFERS/BASE BASE BASE/TABLE", None),
        ("base.volgnr", "REFERS REFERS/BASE BASE BASE/TABLE", None),
        ("base", "REFERS REFERS/BASE BASE BASE/TABLE", None),  # uses id internally
        # This needs access to both the dataset and the table.
        ("base.id", "REFERS REFERS/BASE BASE", PermissionDenied),
        ("base.id", "REFERS REFERS/BASE BASE/TABLE", PermissionDenied),
        # Just mentioning the relation name as the field name isn't enough.
        # The baseId syntax works with composite keys.
        # ("baseId", "REFERS REFERS/BASE BASE BASE/ID", PermissionDenied),
        # ("baseId", "REFERS REFERS/BASE BASE BASE/ID BASE/VOLGNR", None),
    ],
)
def test_check_filter_composite(field_name: str, scopes: str, exc_type: type[Exception] | None):
    """Test filter auth/validation with a composite key relation."""
    table_schema = SCHEMA_COMPOSITE.get_table_by_id("refers")
    scopes = UserScopes(query_params={}, request_scopes=scopes.split())

    if exc_type is None:
        assert parser.QueryFilterEngine.to_orm_path(field_name, table_schema, scopes)
    else:
        with pytest.raises(exc_type):
            parser.QueryFilterEngine.to_orm_path(field_name, table_schema, scopes)
