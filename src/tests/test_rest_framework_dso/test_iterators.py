"""Tests for the ``rest_framework_dso.iterators`` module."""

from itertools import cycle

import pytest

from rest_framework_dso.iterators import ChunkedQuerySetIterator, ObservableIterator, peek_iterable

from .models import Category, Movie


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

    @staticmethod
    def _list_observer(list):
        def _listener(item, **kwargs):
            list.append(item)

        return _listener

    def test_final_outcome(self):
        """Prove that the final result is as desired"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator(
            "abcd", observers=[self._list_observer(seen1), self._list_observer(seen2)]
        )
        assert list(observer) == ["a", "b", "c", "d"]

        assert seen1 == ["a", "b", "c", "d"]
        assert seen1 == seen2
        assert bool(observer)

    def test_streaming(self):
        """Prove that results are collected during iterations"""
        seen1 = []
        seen2 = []

        observer = ObservableIterator(
            "abcd", observers=[self._list_observer(seen1), self._list_observer(seen2)]
        )
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

    def test_empty_bool(self):
        empty = []

        def _is_empty(**kwargs):
            empty.append(True)

        observer = ObservableIterator([], [], [_is_empty])
        assert not observer
        assert empty == [True]
        with pytest.raises(StopIteration):
            next(observer)
        assert empty == [True]  # no new event was raised

    def test_empty_loop(self):
        empty = []

        def _is_empty(**kwargs):
            empty.append(True)

        observer = ObservableIterator([], [], [_is_empty])
        with pytest.raises(StopIteration):
            next(observer)
        assert empty == [True]  # event was raised
        with pytest.raises(StopIteration):
            next(observer)
        assert not observer
        assert empty == [True]  # no new event was raised


def test_peek_iterable():
    first, items = peek_iterable([1, 2, 3])
    assert first == 1
    assert list(items) == [1, 2, 3]
    assert list(items) == []  # generator is consumed
