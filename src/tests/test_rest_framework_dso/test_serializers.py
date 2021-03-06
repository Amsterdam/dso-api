import pytest
from django.contrib.gis.gdal import GDAL_VERSION
from django.db import connection
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from rest_framework_dso.crs import RD_NEW, WGS84
from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.renderers import HALJSONRenderer
from rest_framework_dso.serializers import DSOModelSerializer

from .models import Category, Location, Movie


class CategorySerializer(DSOModelSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOModelSerializer):
    category = EmbeddedField(CategorySerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id"]


class LocationSerializer(DSOModelSerializer):
    class Meta:
        model = Location
        fields = ["geometry"]


@pytest.mark.django_db
def test_serializer_single(drf_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(
        instance=movie, fields_to_expand=["category"], context={"request": drf_request}
    )
    assert serializer.data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "_embedded": {"category": {"name": "bar"}},
    }


@pytest.mark.django_db
def test_serializer_many(drf_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(
        many=True,
        instance=[movie],
        fields_to_expand=["category"],
        context={"request": drf_request},
    )
    assert serializer.data == {
        "movie": [{"name": "foo123", "category_id": movie.category_id}],
        "category": [{"name": "bar"}],
    }


@pytest.mark.django_db
def test_serializer_embed_with_missing_relations(drf_request):
    """Prove that the serializer can embed data (for the detail page)"""

    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO test_rest_framework_dso_movie (name, category_id) VALUES ('Test', 333);"
    )
    movie = Movie.objects.get(name="Test")

    serializer = MovieSerializer(
        many=True,
        instance=[movie],
        fields_to_expand=["category"],
        context={"request": drf_request},
    )
    assert serializer.data == {
        "movie": [{"name": "Test", "category_id": movie.category_id}],
        "category": [],
    }

    # Cleanup needed to make Django happy.
    cursor.execute("DELETE FROM test_rest_framework_dso_movie")


@pytest.mark.django_db
def test_pagination_many(drf_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    queryset = Movie.objects.all()

    serializer = MovieSerializer(
        many=True,
        instance=queryset,
        fields_to_expand=["category"],
        context={"request": drf_request},
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
        "_embedded": {
            "movie": [{"name": "foo123", "category_id": movie.category_id}],
            "category": [{"name": "bar"}],
        },
        "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
    }
    assert response["X-Total-Count"] == "1"
    assert response["X-Pagination-Count"] == "1"
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"


@pytest.mark.django_db
def test_fields_limit_works(api_rf, movie):
    """Prove that serializer can limit output fields."""
    django_request = api_rf.get("/", {"fields": "name"})
    request = Request(django_request)
    request.accepted_renderer = HALJSONRenderer()

    queryset = Movie.objects.all()
    serializer = MovieSerializer(many=True, instance=queryset, context={"request": request})
    paginator = DSOPageNumberPagination()
    paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(serializer.data)

    assert response.data == {
        "_links": {
            "self": {"href": "http://testserver/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "_embedded": {"movie": [{"name": "foo123"}]},
        "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
    }
    assert response["X-Total-Count"] == "1"
    assert response["X-Pagination-Count"] == "1"
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"


@pytest.mark.django_db
def test_fields_limit_by_incorrect_field_gives_error(api_rf, movie):
    """Prove that serializer can limit output fields."""
    django_request = api_rf.get("/", {"fields": "batman"})
    request = Request(django_request)
    queryset = Movie.objects.all()

    serializer = MovieSerializer(many=True, instance=queryset, context={"request": request})
    with pytest.raises(ValidationError) as exec_info:
        # Error is delayed until serialier is evaulated,
        #  as fields limit is performed on Single serializer level.
        repr(serializer)

    assert "'batman' is not one of available options" in str(exec_info.value)


@pytest.mark.django_db
def test_location(drf_request, location):
    """Prove that the serializer recorgnizes crs"""

    serializer = LocationSerializer(
        instance=location,
        fields_to_expand=[],
        context={"request": drf_request},
    )
    data = serializer.data
    assert data["geometry"]["coordinates"] == [10.0, 10.0]

    # Serializer assigned 'response_content_crs' (auto detected)
    assert drf_request.response_content_crs == RD_NEW


@pytest.mark.django_db
def test_location_transform(drf_request, location):
    """Prove that the serializer transforms crs"""

    drf_request.accept_crs = WGS84
    serializer = LocationSerializer(
        instance=location,
        fields_to_expand=[],
        context={"request": drf_request},
    )
    data = serializer.data

    # The lat/lon ordering that is used by the underlying GDAL library
    #

    expected = [3.313687692711974, 47.97485812241689]

    # From: https://gdal.org/tutorials/osr_api_tut.html#crs-and-axis-order
    # Starting with GDAL 3.0, the axis order mandated by the authority
    # defining a CRS is by default honoured by the OGRCoordinateTransformation class,
    # and always exported in WKT1.
    # Consequently CRS created with the “EPSG:4326” or “WGS84”
    # strings use the latitude first, longitude second axis order.
    if GDAL_VERSION >= (3, 0):
        expected = expected[::-1]
    rounder = lambda p: [round(c, 6) for c in p]
    assert rounder(data["geometry"]["coordinates"]) == rounder(expected)

    # Serializer assigned 'response_content_crs' (used accept_crs)
    assert drf_request.response_content_crs == WGS84
