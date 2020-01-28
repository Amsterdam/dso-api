import pytest
from rest_framework.request import Request

from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.serializers import DSOSerializer

from .models import Category, Movie


@pytest.fixture
def category() -> Category:
    return Category.objects.create(name="bar")


@pytest.fixture
def movie(category) -> Movie:
    return Movie.objects.create(name="foo123", category=category)


class CategorySerializer(DSOSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOSerializer):
    category = EmbeddedField(CategorySerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id"]


@pytest.mark.django_db
def test_serializer_single(movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(instance=movie, fields_to_expand=["category"])
    assert serializer.data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "_embedded": {"category": {"name": "bar"},},
    }


@pytest.mark.django_db
def test_serializer_many(movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(
        many=True, instance=[movie], fields_to_expand=["category"]
    )
    assert serializer.data == {
        "results": [{"name": "foo123", "category_id": movie.category_id},],
        "category": [{"name": "bar"},],
    }


@pytest.mark.django_db
def test_pagination_many(api_rf, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    django_request = api_rf.get("/")
    request = Request(django_request)
    queryset = Movie.objects.all()

    serializer = MovieSerializer(
        many=True, instance=queryset, fields_to_expand=["category"]
    )
    paginator = DSOPageNumberPagination()
    paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(serializer.data)

    assert response.data == {
        "_links": {
            "self": {"href": "http://testserver/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "count": 1,
        "page_size": 20,
        "_embedded": {
            "results": [{"name": "foo123", "category_id": movie.category_id},],
            "category": [{"name": "bar"},],
        },
    }
