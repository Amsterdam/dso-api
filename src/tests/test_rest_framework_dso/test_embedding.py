"""Tests for the ``rest_framework_dso.embedding`` module.

The other embedding tests can be found under "test_serializers" and "test_views".
"""

from rest_framework_dso.embedding import get_all_embedded_field_names
from rest_framework_dso.utils import group_dotted_names

from .serializers import MovieSerializer


def test_group_dotted_names():
    """Test whether the nested ?_expandScope can be parsed to a tree."""
    result = group_dotted_names(
        [
            "user",
            "user.group",
            "user.permissions",
            "group",
            "group.permissions",
        ]
    )
    assert result == {
        "user": {
            "group": {},
            "permissions": {},
        },
        "group": {
            "permissions": {},
        },
    }


def test_get_all_embedded_field_names():
    """Prove that all embedded fields are found. This is the basis for ?_expand=true."""
    result = get_all_embedded_field_names(MovieSerializer)
    assert result == {
        "actors": {
            "last_updated_by": {},
        },
        "category": {
            "last_updated_by": {},
        },
    }
