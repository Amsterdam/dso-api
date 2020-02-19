import pytest
from django.urls import path
from rest_framework import generics
from rest_framework.exceptions import ValidationError, ErrorDetail

from rest_framework_dso.fields import EmbeddedField
from rest_framework_dso.serializers import DSOSerializer
from rest_framework_dso.views import get_invalid_params
from .models import Category, Movie


class CategorySerializer(DSOSerializer):
    class Meta:
        model = Category
        fields = ["name"]


class MovieSerializer(DSOSerializer):
    category = EmbeddedField(CategorySerializer)

    class Meta:
        model = Movie
        fields = ["name", "category_id"]


class MovieDetailAPIView(generics.RetrieveAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class MovieListAPIView(generics.ListAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


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
            "movie": [{"name": "foo123", "category_id": movie.category_id}],
            "category": [{"name": "bar"}],
        },
    }
    assert response["Content-Type"] == "application/hal+json"


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
