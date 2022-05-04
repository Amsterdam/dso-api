from datetime import date

import pytest
from django.http import QueryDict

from rest_framework_dso.filters import DSOFilterSet
from .models import Movie


class TestDSOFilterSet:
    class MovieFilterSet(DSOFilterSet):
        class Meta:
            model = Movie
            fields = {
                "name": ["exact"],
                "category_id": ["exact", "in", "not"],
                "date_added": ["exact", "lt", "lte", "gt", "gte", "not"],
                "url": ["exact", "isnull", "not", "isempty", "like"],
            }

    @pytest.fixture
    def movie1(self, category):
        return Movie.objects.create(name="movie1", category=category, date_added=date(2020, 2, 1))

    @pytest.fixture
    def movie2(self):
        return Movie.objects.create(
            name="movie2", date_added=date(2020, 3, 1), url="http://example.com/someurl"
        )

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "comparison",
        [
            # Date less than
            ({"date_added[lt]": "2020-2-10"}, {"movie1"}),
            ({"date_added[lt]": "2020-3-1"}, {"movie1"}),
            ({"date_added[lte]": "2020-3-1"}, {"movie1", "movie2"}),
            # Date less than full datetime
            ({"date_added[lt]": "2020-3-1T23:00:00"}, {"movie1", "movie2"}),
            # Date greater than
            ({"date_added[gt]": "2020-2-10"}, {"movie2"}),
            ({"date_added[gt]": "2020-3-1"}, set()),
            ({"date_added[gte]": "2020-3-1"}, {"movie2"}),
            # Not (can be repeated for "AND NOT" testing)
            ({"date_added[not]": "2020-2-1"}, {"movie2"}),
            (QueryDict("date_added[not]=2020-2-1&date_added[not]=2020-3-1"), set()),
            # URLs have string-like comparison operators
            ({"url[like]": "http:*"}, {"movie2"}),
            ({"url[isnull]": "true"}, {"movie1"}),
        ],
    )
    def test_filter_logic(self, movie1, movie2, comparison):
        filter_data, expect = comparison
        filterset = self.MovieFilterSet(filter_data)
        assert filterset.is_valid(), filterset.errors
        qs = filterset.filter_queryset(Movie.objects.all())
        assert {obj.name for obj in qs} == expect, str(qs.query)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "comparison",
        [
            # IN filter
            ({"category_id[in]": "{cat_id}"}, {"movie1"}),  # test ID
            ({"category_id[in]": "{cat_id},{cat_id}"}, {"movie1"}),  # test comma
            ({"category_id[in]": "97,98,{cat_id}"}, {"movie1"}),  # test invalid IDs
            ({"category_id[in]": "97,98,99"}, set()),  # test all invalid IDs
            # NOT filter
            ({"category_id[not]": "{cat_id}"}, {"movie2"}),
            ({"category_id[not]": "99"}, {"movie1", "movie2"}),
        ],
    )
    def test_foreignkey(self, movie1, movie2, category, comparison):
        filter_data, expect = comparison
        filter_data = {
            field: value.format(cat_id=category.pk) for field, value in filter_data.items()
        }

        filterset = self.MovieFilterSet(filter_data)
        assert filterset.is_valid(), filterset.errors
        qs = filterset.filter_queryset(Movie.objects.all())
        assert {obj.name for obj in qs} == expect, str(qs.query)
