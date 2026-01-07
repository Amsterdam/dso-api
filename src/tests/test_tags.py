from dataclasses import dataclass

import pytest

from dso_api.templatetags.dso_api_tags import TemplateSyntaxError, print_scopes


@dataclass
class Schema:
    auth: frozenset[str]


def test_print_scopes_fails_without_schema():
    with pytest.raises(TemplateSyntaxError):
        print_scopes("")


def test_print_scopes_public():
    schema = Schema(frozenset(["OPENBAAR"]))
    assert print_scopes(schema) == "Geen; dit is openbare data."


def test_print_scopes_multiple():
    schema1 = Schema(frozenset(["PS/1"]))
    schema2 = Schema(frozenset(["PS/2", "PS/3"]))
    schema3 = Schema(frozenset(["OPENBAAR"]))

    assert print_scopes(schema1, schema2, schema3) == "PS/1, PS/2, PS/3"
