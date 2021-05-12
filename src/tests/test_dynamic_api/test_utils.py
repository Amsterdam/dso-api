import pytest

from dso_api.dynamic_api.utils import resolve_model_lookup, split_on_separator
from tests.test_rest_framework_dso import models


@pytest.mark.parametrize(
    "instr,result",
    [
        ("aa_bb", ["aa", "bb"]),
        ("aa.bb", ["aa", "bb"]),
        ("aa.bb.cc", ["aa.bb", "cc"]),
        ("aa_bb.cc", ["aa_bb", "cc"]),
        ("aa.bb_cc", ["aa.bb", "cc"]),
    ],
)
def test_split(instr, result):
    assert split_on_separator(instr) == result


def _assert_lookup(start_model, lookup, expect):
    # Making repeated assertions easier.
    result = resolve_model_lookup(start_model, lookup)
    assert result == expect, f"Failed resolving {start_model.__name__}.{lookup.replace('__', '.')}"
    assert result[0] is expect[0]  # Confirm object references too


def test_resolve_model_lookup():
    """Prove that Django model lookups can be analyzed correctly."""
    resolve_model_lookup.cache_clear()

    # Test forward relations (using "is" test to conform object references)
    _assert_lookup(models.Movie, "category", (models.Category, False))
    _assert_lookup(models.Movie, "category__last_updated_by", (models.MovieUser, False))

    # Testing M2M relations
    _assert_lookup(models.Movie, "actors", (models.Actor, True))
    _assert_lookup(models.Movie, "actors__last_updated_by", (models.MovieUser, False))

    # Test reverse relations (OneToMany)
    _assert_lookup(models.MovieUser, "categories_updated", (models.Category, True))
    _assert_lookup(models.MovieUser, "categories_updated__movies", (models.Movie, True))

    # Test reverse relations (ManyToMany)
    _assert_lookup(models.Actor, "movies", (models.Movie, True))
    _assert_lookup(models.Actor, "movies__category", (models.Category, False))
