from datetime import datetime

import pytest
from django.urls import path
from rest_framework import generics
from rest_framework.exceptions import ValidationError, ErrorDetail

from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.filters import DSOFilterSet
from rest_framework_dso.serializers import DSOSerializer
from rest_framework_dso.views import DSOViewMixin, get_invalid_params
from .models import Category, Movie


class CategorySerializer(DSOSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOSerializer):
    category = EmbeddedField(CategorySerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id", "date_added"]


class MovieFilterSet(DSOFilterSet):
    class Meta:
        model = Movie
        fields = ["name", "date_added"]


class MovieDetailAPIView(generics.RetrieveAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class MovieListAPIView(DSOViewMixin, generics.ListAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()
    filterset_class = MovieFilterSet


urlpatterns = [
    path("v1/movies", MovieListAPIView.as_view(), name="movies-list"),
    path("v1/movies/<pk>", MovieDetailAPIView.as_view(), name="movies-detail"),
]

pytestmark = [pytest.mark.urls(__name__)]  # enable for all tests in this file


@pytest.mark.django_db
@pytest.mark.parametrize("expand", ["true", "category"])
def test_detail_expand_true(api_client, movie, expand):
    """Prove that ?expand=true and ?expand=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get(f"/v1/movies/{movie.pk}", data={"expand": expand})
    assert response.data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "date_added": None,
        "_embedded": {"category": {"name": "bar"}},
    }
    assert response["Content-Type"] == "application/hal+json"


@pytest.mark.django_db
def test_detail_expand_unknown_field(api_client, movie):
    """Prove that ?expand=true and ?expand=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get(f"/v1/movies/{movie.pk}", data={"expand": "foobar"})
    assert response.status_code == 400, response.data
    assert response.json() == {
        "status": 400,
        "type": "urn:apiexception:parse_error",
        "detail": (
            "Eager loading is not supported for field 'foobar', "
            "available options are: category"
        ),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("expand", ["true", "category"])
def test_list_expand_true(api_client, movie, expand):
    """Prove that ?expand=true and ?expand=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get("/v1/movies", data={"expand": expand})
    assert response.data == {
        "_links": {
            "self": {"href": "http://testserver/v1/movies"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "count": 1,
        "page_size": 20,
        "_embedded": {
            "movie": [
                {"name": "foo123", "category_id": movie.category_id, "date_added": None}
            ],
            "category": [{"name": "bar"}],
        },
    }
    assert response["Content-Type"] == "application/hal+json"


@pytest.mark.django_db
class TestListFilters:
    """Prove that filtering works as expected."""

    @staticmethod
    def test_list_filter_wildcard(api_client):
        """Prove that ?name=foo also works with wildcards"""
        Movie.objects.create(name="foo123")
        Movie.objects.create(name="test")

        response = api_client.get(f"/v1/movies", data={"name": "foo1?3"})
        assert response.status_code == 200, response
        assert response.data["count"] == 1
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime(api_client):
        """Prove that datetime fields can be queried using a single data value"""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        response = api_client.get(f"/v1/movies", data={"date_added": "2020-01-01"})
        assert response.status_code == 200, response
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert response.data["count"] == 1, names
        assert names == ["foo123"]
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime_invalid(api_client):
        """Prove that invalid input is captured, and returns a proper error response."""
        response = api_client.get(f"/v1/movies", data={"date_added": "2020-01-fubar"})
        assert response.status_code == 400, response
        assert response["Content-Type"] == "application/problem+json", response
        assert response.json() == {
            "type": "urn:apiexception:invalid",
            "detail": "Invalid input.",
            "status": 400,
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:invalid",
                    "name": "date_added",
                    "reason": "Enter a valid date.",
                }
            ],
            "x-validation-errors": {"date_added": ["Enter a valid date."]},
        }


@pytest.mark.django_db
class TestListOrdering:
    """Prove that the ordering works as expected."""

    @staticmethod
    def test_list_ordering_name(api_client):
        """Prove that ?sorteer=... works on the list view."""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        # Sort descending by name
        response = api_client.get(f"/v1/movies", data={"sorteer": "-name"})
        assert response.status_code == 200, response.json()
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_date(api_client):
        """Prove that ?sorteer=... works on the list view."""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        # Sort descending by name
        response = api_client.get(f"/v1/movies", data={"sorteer": "-date_added"})
        assert response.status_code == 200, response.json()
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_invalid(api_client, category, django_assert_num_queries):
        """Prove that ?sorteer=... only works on a fixed set of fields (e.g. not on FK's)."""
        response = api_client.get(f"/v1/movies", data={"sorteer": "category"})
        assert response.status_code == 400, response.json()
        assert response.json() == {
            "type": "urn:apiexception:invalid",
            "detail": "Invalid input.",
            "status": 400,
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:order-by",
                    "name": None,
                    "reason": "Invalid sort fields: category",
                }
            ],
            "x-validation-errors": ["Invalid sort fields: category"],
        }


class TestExceptionHandler:
    """Prove that the exception handler works as expected"""

    @staticmethod
    def test_simple_validation_error():
        """Prove that the API generates the proper "invalid-params" section
        for the application/problem+json response.
        """
        exception = ValidationError(
            {"date_field": [ErrorDetail("Enter a valid date/time.", code="invalid")]}
        )
        result = get_invalid_params(exception, exception.detail)
        assert result == [
            {
                "type": "urn:apiexception:invalid:invalid",
                "name": "date_field",
                "reason": "Enter a valid date/time.",
            }
        ]

    @staticmethod
    def test_complex_validation_error():
        """Prove that the API can handle the complex DRF exception trees."""
        exception = ValidationError(
            {
                "persons": [
                    {
                        "email": [
                            ErrorDetail("Already used", code="unique"),
                            ErrorDetail("Invalid domain", code="invalid"),
                        ]
                    }
                ]
            }
        )
        result = get_invalid_params(exception, exception.detail)
        assert result == [
            {
                "type": "urn:apiexception:invalid:unique",
                "name": "persons[0].email",
                "reason": "Already used",
            },
            {
                "type": "urn:apiexception:invalid:invalid",
                "name": "persons[0].email",
                "reason": "Invalid domain",
            },
        ]
