from pathlib import Path
from typing import Optional

import pytest
from django.core.exceptions import PermissionDenied
from schematools.permissions import UserScopes
from schematools.utils import dataset_schema_from_path

from dso_api.dynamic_api.permissions import FilterSyntaxError, _check_field_access

SCHEMA_SIMPLE = dataset_schema_from_path(
    Path(__file__).parent.parent / "files" / "relationauth.json"
)
SCHEMA_COMPOSITE = dataset_schema_from_path(
    Path(__file__).parent.parent / "files" / "relationauthcomposite.json"
)


@pytest.mark.parametrize(
    ["field_name", "scopes", "exc_type"],
    [
        ("", "", FilterSyntaxError),
        ("name", "REFERS REFERS/NAME", None),
        ("baseId", "REFERS REFERS/NAME", PermissionDenied),
        ("baseId", "REFERS REFERS/BASE", PermissionDenied),
        ("baseId", "REFERS REFERS/BASE BASE", PermissionDenied),
        ("baseId", "REFERS REFERS/BASE BASE/ID", PermissionDenied),
        # ("baseId", "REFERS BASE BASE/ID", PermissionDenied),
        # ("baseId", "REFERS/BASE BASE BASE/ID", PermissionDenied),
        ("base", "REFERS REFERS/BASE BASE BASE/ID", FilterSyntaxError),
        ("baseId", "REFERS REFERS/BASE BASE BASE/ID", None),
    ],
)
def test_check_filter_simple(field_name: str, scopes: str, exc_type: Optional[type]):
    """Test filter auth/validation with a simple-key relation."""
    schema = SCHEMA_SIMPLE.get_table_by_id("refers")

    scopes = UserScopes(query_params={}, request_scopes=scopes.split())
    if exc_type is None:
        _check_field_access(field_name, scopes, schema)
    else:
        with pytest.raises(exc_type):
            _check_field_access(field_name, scopes, schema)


@pytest.mark.parametrize(
    ["field_name", "scopes", "exc_type"],
    [
        # Reference to relation field, e.g., base=$id:$volgnr
        # ("base", "REFERS REFERS/BASE BASE BASE/ID BASE/VOLGNR", None),
        # ("baseId", "REFERS REFERS/BASE BASE BASE/ID", PermissionDenied),
        # ("baseId", "REFERS REFERS/BASE BASE BASE/VOLGNR", PermissionDenied),
        # ("baseId", "REFERS REFERS/BASE BASE BASE/ID BASE/VOLGNR", FilterSyntaxError),
    ],
)
def test_check_filter_composite(field_name: str, scopes: str, exc_type: Optional[type]):
    """Test filter auth/validation with a composite key relation."""
    schema = SCHEMA_COMPOSITE.get_table_by_id("refers")

    scopes = UserScopes(query_params={}, request_scopes=scopes.split())
    if exc_type is None:
        _check_field_access(field_name, scopes, schema)
    else:
        with pytest.raises(exc_type):
            _check_field_access(field_name, scopes, schema)
