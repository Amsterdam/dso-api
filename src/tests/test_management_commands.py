import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from django.core.management import call_command
from jwcrypto.jwk import JWK
from jwcrypto.jwt import JWT
from schematools.contrib.django.models import DynamicModel

from dso_api.dynamic_api.management.commands import implement_constraint


@pytest.mark.django_db
def test_dump_serializers_python_and_nested(router, bommen_dataset, capsys):
    router.reload()

    call_command("dump_serializers")
    python_output = capsys.readouterr().out
    assert "class " in python_output
    assert "class Meta:" in python_output

    call_command("dump_serializers", "--format=nested")
    nested_output = capsys.readouterr().out
    assert nested_output
    assert nested_output != python_output


@pytest.mark.parametrize("validity", [None, 60])
def test_maketoken_outputs_signed_token(settings, capsys, validity):
    jwks = json.loads(Path(__file__).parents[1].joinpath("jwks_test.json").read_text())
    settings.DATAPUNT_AUTHZ["JWKS"] = json.dumps(jwks)

    arguments = ["scope:one", "scope:two", "scope:one"]
    if validity is not None:
        arguments.extend(["--valid", str(validity)])
    call_command("maketoken", *arguments)

    token = capsys.readouterr().out.strip()
    key = JWK(**jwks["keys"][0])
    claims = json.loads(JWT(jwt=token, key=key, algs=["ES256"]).claims)
    assert set(claims["scopes"]) == {"scope:one", "scope:two"}
    assert ("exp" in claims) is (validity is not None)


@pytest.mark.parametrize(
    ("identifier", "contains_slash", "expected_queries", "expected_output"),
    [
        (["id"], False, 2, "Applied constraint"),
        (["id"], True, 0, "Skipping this model"),
        (["id", "other"], False, 0, ""),
    ],
)
def test_implement_constraint(
    monkeypatch, capsys, identifier, contains_slash, expected_queries, expected_output
):
    schema = Mock(
        identifier_fields=[Mock(type="string", python_name="id", db_name="id")],
        identifier=identifier,
        db_name="table_name",
    )
    model = Mock()
    model.table_schema.return_value = schema
    model.objects.filter.return_value.exists.return_value = contains_slash

    monkeypatch.setattr(
        implement_constraint.apps, "all_models", {"app": {"model": model, "plain": object()}}
    )
    monkeypatch.setattr(
        implement_constraint,
        "issubclass",
        lambda candidate, parent: candidate is model and parent is DynamicModel,
        raising=False,
    )
    cursor_context = MagicMock()
    cursor = cursor_context.__enter__.return_value
    monkeypatch.setattr(
        implement_constraint.connection, "cursor", Mock(return_value=cursor_context)
    )

    implement_constraint.Command().handle()

    assert cursor.execute.call_count == expected_queries
    assert expected_output in capsys.readouterr().out
