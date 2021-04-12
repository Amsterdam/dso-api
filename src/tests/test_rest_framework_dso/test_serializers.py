import pytest
from django.db import connection
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from rest_framework_dso.crs import RD_NEW, WGS84
from rest_framework_dso.fields import EmbeddedField, EmbeddedManyToManyField
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.renderers import HALJSONRenderer
from rest_framework_dso.serializers import DSOModelSerializer
from tests.utils import normalize_data, read_response_json

from .models import Actor, Category, Location, Movie


class ActorSerializer(DSOModelSerializer):
    class Meta:
        model = Actor
        fields = ["name"]


class CategorySerializer(DSOModelSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOModelSerializer):
    category = EmbeddedField(CategorySerializer)
    actors = EmbeddedManyToManyField(ActorSerializer)

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
        instance=movie, fields_to_expand=["actors", "category"], context={"request": drf_request}
    )

    data = normalize_data(serializer.data)
    assert data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "_embedded": {
            "actors": [
                {"name": "John Doe"},
                {"name": "Jane Doe"},
            ],
            "category": {"name": "bar"},
        },
    }


@pytest.mark.django_db
def test_serializer_many(drf_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    serializer = MovieSerializer(
        Movie.objects.all(),
        many=True,
        fields_to_expand=["actors", "category"],
        context={"request": drf_request},
    )

    data = normalize_data(serializer.data)
    assert data == {
        "movie": [{"name": "foo123", "category_id": movie.category_id}],
        "actors": [
            {"name": "John Doe"},
            {"name": "Jane Doe"},
        ],
        "category": [{"name": "bar"}],
    }


@pytest.mark.django_db
def test_serializer_embed_with_missing_relations(drf_request):
    """Prove that the serializer can embed data (for the detail page)"""

    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO test_rest_framework_dso_movie (name, category_id) VALUES ('Test', 333);"
    )
    try:
        movie = Movie.objects.get(name="Test")

        serializer = MovieSerializer(
            Movie.objects.all(),
            many=True,
            fields_to_expand=["category"],
            context={"request": drf_request},
        )

        data = normalize_data(serializer.data)
        assert data == {
            "movie": [{"name": "Test", "category_id": movie.category_id}],
            "category": [],
        }
    finally:
        # Make sure the cleanup happens or unit tests report this error
        # instead of the actual assertion error.
        cursor.execute("DELETE FROM test_rest_framework_dso_movie WHERE category_id=333")


@pytest.mark.django_db
def test_pagination_many(drf_request, movie):
    """Prove that the serializer can embed data (for the detail page)"""
    queryset = Movie.objects.all()

    serializer = MovieSerializer(
        many=True,
        instance=queryset,
        fields_to_expand=["actors", "category"],
        context={"request": drf_request},
    )
    paginator = DSOPageNumberPagination()
    paginator.paginate_queryset(queryset, drf_request)
    response = paginator.get_paginated_response(serializer.data)

    # Since response didn't to through APIView.finalize_response(), fix that:
    response.accepted_renderer = drf_request.accepted_renderer
    response.accepted_media_type = drf_request.accepted_renderer.media_type
    response.renderer_context = {"request": drf_request}
    data = read_response_json(response.render())

    assert data == {
        "_links": {
            "self": {"href": "http://testserver/v1/dummy/"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "_embedded": {
            "movie": [{"name": "foo123", "category_id": movie.category_id}],
            "actors": [
                {"name": "John Doe"},
                {"name": "Jane Doe"},
            ],
            "category": [{"name": "bar"}],
        },
        "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
    }
    assert response["X-Total-Count"] == "1"
    assert response["X-Pagination-Count"] == "1"
    assert response["X-Pagination-Page"] == "1"
    assert response["X-Pagination-Limit"] == "20"


@pytest.mark.django_db
@pytest.mark.parametrize("fields", ["name", "-category_id"])  # -category_id leaves only name.
def test_fields_limit_works(api_rf, movie, fields):
    """Prove that serializer can limit output fields."""
    django_request = api_rf.get("/", {"fields": fields})
    drf_request = Request(django_request)
    drf_request.accepted_renderer = HALJSONRenderer()

    queryset = Movie.objects.all()
    serializer = MovieSerializer(many=True, instance=queryset, context={"request": drf_request})
    paginator = DSOPageNumberPagination()
    paginator.paginate_queryset(queryset, drf_request)
    response = paginator.get_paginated_response(serializer.data)

    # Since response didn't to through APIView.finalize_response(), fix that:
    response.accepted_renderer = drf_request.accepted_renderer
    response.accepted_media_type = drf_request.accepted_renderer.media_type
    response.renderer_context = {"request": drf_request}
    data = read_response_json(response.render())

    assert data == {
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
@pytest.mark.parametrize("fields", ["batman", "-batman"])
def test_fields_limit_by_incorrect_field_gives_error(api_rf, movie, fields):
    """Requesting non-existent fields is an error."""
    django_request = api_rf.get("/", {"fields": fields})
    request = Request(django_request)
    queryset = Movie.objects.all()

    serializer = MovieSerializer(many=True, instance=queryset, context={"request": request})
    with pytest.raises(ValidationError) as exec_info:
        # Error is delayed until serialier is evaulated,
        #  as fields limit is performed on Single serializer level.
        repr(serializer)

    assert "'batman' not among the available options" in str(exec_info.value)


@pytest.mark.django_db
def test_fields_limit_mixed(api_rf, movie):
    """Positive and negative field specifiers may not be mixed."""
    request = Request(api_rf.get("/", {"fields": "name,-category_id"}))
    queryset = Movie.objects.all()

    serializer = MovieSerializer(many=True, instance=queryset, context={"request": request})
    with pytest.raises(ValidationError) as exec_info:
        # Error is delayed until serialier is evaulated,
        #  as fields limit is performed on Single serializer level.
        repr(serializer)

    assert "not possible to combine" in str(exec_info.value)


@pytest.mark.django_db
def test_location(drf_request, location):
    """Prove that the serializer recorgnizes crs"""

    serializer = LocationSerializer(
        instance=location,
        fields_to_expand=[],
        context={"request": drf_request},
    )
    data = normalize_data(serializer.data)
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
    data = normalize_data(serializer.data)

    # The lat/lon ordering that is used by the underlying GDAL library,
    # should always be consistent. (so axis ordering of GDAL 3 does not matter).
    #
    # From: https://gdal.org/tutorials/osr_api_tut.html#crs-and-axis-order
    # Starting with GDAL 3.0, the axis order mandated by the authority
    # defining a CRS is by default honoured by the OGRCoordinateTransformation class (...).
    # Consequently CRS created with the “EPSG:4326” or “WGS84”
    # strings use the latitude first, longitude second axis order.
    rounder = lambda p: [round(c, 6) for c in p]
    assert rounder(data["geometry"]["coordinates"]) == [3.313688, 47.974858]

    # Serializer assigned 'response_content_crs' (used accept_crs)
    assert drf_request.response_content_crs == WGS84
