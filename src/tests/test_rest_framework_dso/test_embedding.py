"""Tests for the ``rest_framework_dso.embedding`` module.

The other embedding tests can be found under "test_serializers" and "test_views".
"""

from itertools import cycle

import pytest

from rest_framework_dso.embedding import (
    ChunkedQuerySetIterator,
    ObservableIterator,
    get_all_embedded_field_names,
)
from rest_framework_dso.utils import group_dotted_names

from .models import Category, Movie
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


@pytest.mark.django_db
class TestChunkedQuerySetIterator:
    """Test whether the queryset chunking works as advertised."""

    @pytest.fixture()
    def movie_data(self):
        categories = cycle(
            [
                Category.objects.create(pk=1, name="category1"),
                Category.objects.create(pk=2, name="category2"),
            ]
        )

        for i in range(20):
            Movie.objects.create(pk=i, name=f"Movie {i}", category=next(categories))

    def test_chunked(self, movie_data, django_assert_num_queries):
        """Test whether the queryset chunking works as expected"""
        queryset = Movie.objects.prefetch_related("category").order_by("pk")
        iterator = ChunkedQuerySetIterator(queryset, chunk_size=6, sql_chunk_size=6)

        # Only needs 2 queries: the movies + prefetch categories
        with django_assert_num_queries(2):
            data = list(iterator)

        # Last chunk also fetched completely:
        assert len(data) == 20, data

        # Foreign key caches are filled, so can read data without queries.
        with django_assert_num_queries(0):
            summary = [(movie.name, movie.category.name) for movie in data]

        # See that the data is properly linked
        assert summary == [
            ("Movie 0", "category1"),
            ("Movie 1", "category2"),
            ("Movie 2", "category1"),
            ("Movie 3", "category2"),
            ("Movie 4", "category1"),
            ("Movie 5", "category2"),
            ("Movie 6", "category1"),
            ("Movie 7", "category2"),
            ("Movie 8", "category1"),
            ("Movie 9", "category2"),
            ("Movie 10", "category1"),
            ("Movie 11", "category2"),
            ("Movie 12", "category1"),
            ("Movie 13", "category2"),
            ("Movie 14", "category1"),
            ("Movie 15", "category2"),
            ("Movie 16", "category1"),
            ("Movie 17", "category2"),
            ("Movie 18", "category1"),
            ("Movie 19", "category2"),
        ]


class TestObservableIterator:
    """Test whether the iterator observing works as advertised."""

    def test_final_outcome(self):
        """Prove that the final result is as desired"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator("abcd", observers=[seen1.append, seen2.append])
        assert list(observer) == ["a", "b", "c", "d"]

        assert seen1 == ["a", "b", "c", "d"]
        assert seen1 == seen2
        assert bool(observer)

    def test_streaming(self):
        """Prove that results are collected during iterations"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator("abcd", observers=[seen1.append, seen2.append])
        assert bool(observer)  # Prove that inspecting first doesn't break

        assert next(observer) == "a"
        assert seen1 == ["a"]
        assert seen1 == seen2
        assert bool(observer)

        assert next(observer) == "b"
        assert seen1 == ["a", "b"]
        assert seen1 == seen2
        assert bool(observer)

        # Consume the rest
        assert list(observer) == ["c", "d"]
        assert seen1 == ["a", "b", "c", "d"]
        assert seen1 == seen2
        assert bool(observer)
