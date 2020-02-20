import pytest
from django.db.models import Value

from rest_framework_dso.filters import Wildcard
from .models import Category


class TestWildcard:
    def wildcard_escape(self, word):
        # Quick shortcut to test the escaping of the lookup class
        lookup = Wildcard("field", Value(word))
        rhs, params = lookup.get_db_prep_lookup(word, connection=None)
        return params[0]

    def test_escapes_words(self):
        assert self.wildcard_escape("foo*") == "foo%"
        assert self.wildcard_escape("fo?o") == r"fo_o"
        assert self.wildcard_escape("fo%o") == r"fo\%o"
        assert self.wildcard_escape("fo%o_") == r"fo\%o\_"
        assert self.wildcard_escape("f?_oob%ar*") == r"f_\_oob\%ar%"

    @pytest.mark.django_db
    def test_like_filter_sql(self, django_assert_num_queries):
        with django_assert_num_queries(1) as context:
            # using str(qs.query) doesn't apply database-level escaping,
            # so running the query instead to get the actual executed query.
            list(Category.objects.filter(name__wildcard="foo*bar?"))

        sql = context.captured_queries[0]["sql"]
        assert r"""."name" LIKE 'foo%bar_'""" in sql
