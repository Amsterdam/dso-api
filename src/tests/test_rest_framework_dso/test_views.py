import json
from datetime import datetime

import pytest
from django.urls import path
from rest_framework import generics
from rest_framework.exceptions import ValidationError, ErrorDetail

from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.filters import DSOFilterSet
from rest_framework_dso.serializers import DSOModelSerializer
from rest_framework_dso.views import DSOViewMixin, get_invalid_params
from .models import Category, Movie


class CategorySerializer(DSOModelSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOModelSerializer):
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
@pytest.mark.parametrize("params", [{"_expand": "true"}, {"_expandScope": "category"}])
def test_detail_expand_true(api_client, movie, params):
    """Prove that ?_expand=true and ?_expand=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get(f"/v1/movies/{movie.pk}", data=params)
    assert response.data == {
        "name": "foo123",
        "category_id": movie.category_id,
        "date_added": None,
        "_embedded": {"category": {"name": "bar"}},
    }
    assert response["Content-Type"] == "application/hal+json"


@pytest.mark.django_db
def test_detail_expand_unknown_field(api_client, movie):
    """Prove that ?_expand=true and ?_expandScope=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get(f"/v1/movies/{movie.pk}", data={"_expandScope": "foobar"})
    assert response.status_code == 400, response.data
    assert response.json() == {
        "status": 400,
        "type": "urn:apiexception:parse_error",
        "title": "Malformed request.",
        "detail": (
            "Eager loading is not supported for field 'foobar', "
            "available options are: category"
        ),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("params", [{"_expand": "true"}, {"_expandScope": "category"}])
def test_list_expand_true(api_client, movie, params):
    """Prove that ?_expand=true and ?_expandScope=category both work for the detail view.

    This also tests the parameter expansion within the view logic.
    """
    response = api_client.get("/v1/movies", data=params)
    assert response.data == {
        "_links": {
            "self": {"href": "http://testserver/v1/movies"},
            "next": {"href": None},
            "previous": {"href": None},
        },
        "_embedded": {
            "movie": [
                {"name": "foo123", "category_id": movie.category_id, "date_added": None}
            ],
            "category": [{"name": "bar"}],
        },
        "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
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

        response = api_client.get("/v1/movies", data={"name": "foo1?3"})
        assert response.status_code == 200, response
        assert response.data["page"]["totalElements"] == 1
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime(api_client):
        """Prove that datetime fields can be queried using a single data value"""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        response = api_client.get("/v1/movies", data={"date_added": "2020-01-01"})
        assert response.status_code == 200, response
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert response.data["page"]["totalElements"] == 1, names
        assert names == ["foo123"]
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime_invalid(api_client):
        """Prove that invalid input is captured, and returns a proper error response."""
        response = api_client.get("/v1/movies", data={"date_added": "2020-01-fubar"})
        assert response.status_code == 400, response
        assert response["Content-Type"] == "application/problem+json", response
        assert response.json() == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies?date_added=2020-01-fubar",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:invalid",
                    "name": "date_added",
                    "reason": "Enter a valid ISO date-time, or single date.",
                }
            ],
            "x-validation-errors": {
                "date_added": ["Enter a valid ISO date-time, or single date."]
            },
        }

    @staticmethod
    def test_list_filter_nested_serializer(
        api_client, parkeervakken_parkeervak_model, parkeervakken_regime_model
    ):
        response = api_client.get(
            "/v1/parkeervakken", data={"regimes.inWerkingOp": "08:00"}
        )

        assert response.status_code == 200, response


@pytest.mark.django_db
class TestListOrdering:
    """Prove that the ordering works as expected."""

    @staticmethod
    def test_list_ordering_name(api_client):
        """Prove that ?_sort=... works on the list view."""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        # Sort descending by name
        response = api_client.get("/v1/movies", data={"_sort": "-name"})
        assert response.status_code == 200, response.json()
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_name_old_param(api_client):
        """Prove that ?_sort=... works on the list view."""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        # Sort descending by name
        response = api_client.get("/v1/movies", data={"sorteer": "-name"})
        assert response.status_code == 200, response.json()
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_date(api_client):
        """Prove that ?_sort=... works on the list view."""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        # Sort descending by name
        response = api_client.get("/v1/movies", data={"_sort": "-date_added"})
        assert response.status_code == 200, response.json()
        names = [movie["name"] for movie in response.data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_invalid(api_client, category, django_assert_num_queries):
        """Prove that ?_sort=... only works on a fixed set of fields (e.g. not on FK's)."""
        response = api_client.get("/v1/movies", data={"_sort": "category"})
        assert response.status_code == 400, response.json()
        assert response.json() == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies?_sort=category",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:order-by",
                    "name": "order-by",
                    "reason": "Invalid sort fields: category",
                }
            ],
            "x-validation-errors": ["Invalid sort fields: category"],
        }


@pytest.mark.django_db
class TestLimitFields:
    """Prove that fields limiting works as expected."""

    def test_limit_one_field(self, api_client):
        """Prove that ?_fields=name results in result with only names"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        response = api_client.get("/v1/movies", data={"_fields": "name"})
        assert response.status_code == 200, response.json()
        assert json.dumps(response.data["_embedded"]["movie"]) == json.dumps(
            [{"name": "foo123"}, {"name": "test"}]
        )

    def test_limit_multiple_fields(self, api_client):
        """Prove that ?_fields=name,date results in result with only names and dates"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        response = api_client.get("/v1/movies", data={"_fields": "name,date_added"})
        assert response.status_code == 200, response.json()
        assert json.dumps(response.data["_embedded"]["movie"]) == json.dumps(
            [
                {"name": "foo123", "date_added": None},
                {"name": "test", "date_added": None},
            ]
        )

    def test_incorrect_field_in_fields_results_in_error(self, api_client):
        """Prove that adding invalid name to ?_fields will result in error"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        response = api_client.get("/v1/movies", data={"_fields": "name,date"})
        assert response.status_code == 400, response.json()
        assert response.json() == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies?_fields=name%2Cdate",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:fields",
                    "name": "fields",
                    "reason": "'date' is not one of available options",
                }
            ],
            "x-validation-errors": ["'date' is not one of available options"],
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
