import json
from collections import defaultdict

from dso_api import audit_log


def test_json_encoder():
    encode = audit_log._encoder.encode

    assert encode("foo") == '"foo"'
    assert encode(defaultdict(None, {"foo": 1})) == '{"foo": 1}'
    assert sorted(json.loads(encode(set("abc")))) == ["a", "b", "c"]
    assert encode(frozenset()) == "[]"

    class Custom:
        def __repr__(self):
            return "<Custom()>"

    assert encode(Custom()) == '"<Custom()>"'
