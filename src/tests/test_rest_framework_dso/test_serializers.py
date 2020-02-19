import pytest
from rest_framework.request import Request

from rest_framework_dso.crs import RD_NEW, WGS84
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.serializers import DSOSerializer

from .models import Category, Location, Movie


class CategorySerializer(DSOSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOSerializer):
    category = EmbeddedField(CategorySerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id"]


class LocationSerializer(DSOSerializer):
    class Meta:
        model = Location
        fields = ["geometry"]


@pytest.mark.django_db
def test_serializer_single(movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(instance=movie, fields_to_expand=["category"])
    assert serializer.data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "_embedded": {"category": {"name": "bar"}},
    }


@pytest.mark.django_db
def test_serializer_many(movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(
        many=True, instance=[movie], fields_to_expand=["category"]
    )
    assert serializer.data == {
        "movie": [{"name": "foo123", "category_id": movie.category_id}],
        "category": [{"name": "bar"}],
    }


@pytest.mark.django_db
def test_pagination_many(api_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    drf_request = Request(api_request)
    queryset = Movie.objects.all()

    serializer = MovieSerializer(
        many=True, instance=queryset, fields_to_expand=["category"]
    )
    paginator = DSOPageNumberPagination()
    paginator.paginate_queryset(queryset, drf_request)
    response = paginator.get_paginated_response(serializer.data)

    assert response.data == {
        "_links": {
            "self": {"href": "http://testserver/v1/dummy/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "count": 1,
        "page_size": 20,
        "_embedded": {
            "movie": [{"name": "foo123", "category_id": movie.category_id}],
            "category": [{"name": "bar"}],
        },
    }


@pytest.mark.django_db
def test_location(api_request, location):
    """Prove that the serializer recorgnizes crs"""

    serializer = LocationSerializer(
        instance=location, fields_to_expand=[], context={"request": api_request},
    )
    data = serializer.data
    assert data["geometry"]["coordinates"] == [10.0, 10.0]

    # Serializer assigned 'response_content_crs' (auto detected)
    assert api_request.response_content_crs == RD_NEW


@pytest.mark.django_db
def test_location_transform(api_request, location):
    """Prove that the serializer transforms crs"""

    api_request.accept_crs = WGS84
    serializer = LocationSerializer(
        instance=location, fields_to_expand=[], context={"request": api_request},
    )
    data = serializer.data
    rounder = lambda p: [round(c, 6) for c in p]
    assert rounder(data["geometry"]["coordinates"]) == rounder(
        [3.313687692711974, 47.97485812241689]
    )

    # Serializer assigned 'response_content_crs' (used accept_crs)
    assert api_request.response_content_crs == WGS84
