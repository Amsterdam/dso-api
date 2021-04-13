import json
from datetime import datetime
from html import unescape

import pytest
from django.urls import path
from django.utils.html import strip_tags
from rest_framework import generics
from rest_framework.exceptions import ErrorDetail, ValidationError

from rest_framework_dso import views
from rest_framework_dso.filters import DSOFilterSet
from tests.utils import read_response, read_response_json

from .models import Movie
from .serializers import MovieSerializer


class MovieFilterSet(DSOFilterSet):
    class Meta:
        model = Movie
        fields = ["name", "date_added"]


class MovieDetailAPIView(generics.RetrieveAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class MovieListAPIView(views.DSOViewMixin, generics.ListAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()
    filterset_class = MovieFilterSet


urlpatterns = [
    path("v1/movies", MovieListAPIView.as_view(), name="movies-list"),
    path("v1/movies/<pk>", MovieDetailAPIView.as_view(), name="movies-detail"),
]
handler500 = views.server_error

pytestmark = [pytest.mark.urls(__name__)]  # enable for all tests in this file


@pytest.mark.django_db
class TestExpand:
    @pytest.mark.parametrize("params", [{"_expand": "true"}, {"_expandScope": "actors,category"}])
    def test_detail_expand_true(self, api_client, movie, params):
        """Prove that ?_expand=true and ?_expand=category both work for the detail view.

        This also tests the parameter expansion within the view logic.
        """
        response = api_client.get(f"/v1/movies/{movie.pk}", data=params)
        data = read_response_json(response)
        assert data == {
            "name": "foo123",
            "category_id": movie.category_id,
            "date_added": None,
            "_embedded": {
                "actors": [
                    {"name": "John Doe"},
                    {"name": "Jane Doe"},
                ],
                "category": {"name": "bar"},
            },
        }
        assert response["Content-Type"] == "application/hal+json"

    def test_detail_expand_unknown_field(self, api_client, movie):
        """Prove that ?_expand=true and ?_expandScope=category both work for the detail view.

        This also tests the parameter expansion within the view logic.
        """
        response = api_client.get(f"/v1/movies/{movie.pk}", data={"_expandScope": "foobar"})
        data = read_response_json(response)

        assert response.status_code == 400, data
        assert data == {
            "status": 400,
            "type": "urn:apiexception:parse_error",
            "title": "Malformed request.",
            "detail": (
                "Eager loading is not supported for field 'foobar', "
                "available options are: actors, category"
            ),
        }

    @pytest.mark.parametrize("params", [{"_expand": "true"}, {"_expandScope": "actors,category"}])
    def test_list_expand_true(self, api_client, movie, params):
        """Prove that ?_expand=true and ?_expandScope=category both work for the detail view.

        This also tests the parameter expansion within the view logic.
        """
        response = api_client.get("/v1/movies", data=params)
        data = read_response_json(response)
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/movies"},
                "next": {"href": None},
                "previous": {"href": None},
            },
            "_embedded": {
                "movie": [
                    {"name": "foo123", "category_id": movie.category_id, "date_added": None}
                ],
                "actors": [
                    {"name": "John Doe"},
                    {"name": "Jane Doe"},
                ],
                "category": [{"name": "bar"}],
            },
            "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
        }
        assert response["Content-Type"] == "application/hal+json"

    def test_list_expand_api(self, api_client, movie):
        """Prove that the browsable API also properly renders the generator content."""
        response = api_client.get("/v1/movies", data={"_expand": "true"}, HTTP_ACCEPT="text/html")
        assert response["content-type"] == "text/html; charset=utf-8"
        html = read_response(response)
        assert response["content-type"] == "text/html; charset=utf-8"

        start = html.index("{", html.index("<pre"))
        end = html.rindex("}", start, html.rindex("</pre>")) + 1
        response_preview = unescape(strip_tags(html[start:end]))
        data = json.loads(response_preview)

        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/movies"},
                "next": {"href": None},
                "previous": {"href": None},
            },
            "_embedded": {
                "movie": [
                    {"name": "foo123", "category_id": movie.category_id, "date_added": None}
                ],
                "actors": [
                    {"name": "John Doe"},
                    {"name": "Jane Doe"},
                ],
                "category": [{"name": "bar"}],
            },
            "page": {"number": 1, "size": 20, "totalElements": 1, "totalPages": 1},
        }


@pytest.mark.django_db
class TestListFilters:
    """Prove that filtering works as expected."""

    @staticmethod
    def test_list_filter_wildcard(api_client):
        """Prove that ?name=foo doesn't works with wildcards"""
        Movie.objects.create(name="foo123")
        Movie.objects.create(name="test")

        response = api_client.get("/v1/movies", data={"name": "foo1?3"})
        data = read_response_json(response)
        assert response.status_code == 200, response
        assert data["page"]["totalElements"] == 0
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime(api_client):
        """Prove that datetime fields can be queried using a single data value"""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        response = api_client.get("/v1/movies", data={"date_added": "2020-01-01"})
        data = read_response_json(response)
        assert response.status_code == 200, response
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert data["page"]["totalElements"] == 1, names
        assert names == ["foo123"]
        assert response["Content-Type"] == "application/hal+json"

    @staticmethod
    def test_list_filter_datetime_invalid(api_client):
        """Prove that invalid input is captured, and returns a proper error response."""
        response = api_client.get("/v1/movies", data={"date_added": "2020-01-fubar"})
        assert response.status_code == 400, response
        assert response["Content-Type"] == "application/problem+json", response  # check first
        data = read_response_json(response)
        assert response["Content-Type"] == "application/problem+json", response  # and after
        assert data == {
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
        data = read_response_json(response)

        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_name_old_param(api_client):
        """Prove that ?_sort=... works on the list view."""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        # Sort descending by name
        response = api_client.get("/v1/movies", data={"sorteer": "-name"})
        data = read_response_json(response)

        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_date(api_client):
        """Prove that ?_sort=... works on the list view."""
        Movie.objects.create(name="foo123", date_added=datetime(2020, 1, 1, 0, 45))
        Movie.objects.create(name="test", date_added=datetime(2020, 2, 2, 13, 15))

        # Sort descending by name
        response = api_client.get("/v1/movies", data={"_sort": "-date_added"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        names = [movie["name"] for movie in data["_embedded"]["movie"]]
        assert names == ["test", "foo123"]

    @staticmethod
    def test_list_ordering_invalid(api_client, category, django_assert_num_queries):
        """Prove that ?_sort=... only works on a fixed set of fields (e.g. not on FK's)."""
        response = api_client.get("/v1/movies", data={"_sort": "category"})
        data = read_response_json(response)

        assert response.status_code == 400, data
        assert data == {
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
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["movie"] == [{"name": "foo123"}, {"name": "test"}]

    def test_limit_multiple_fields(self, api_client):
        """Prove that ?_fields=name,date results in result with only names and dates"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        response = api_client.get("/v1/movies", data={"_fields": "name,date_added"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"]["movie"] == [
            {"name": "foo123", "date_added": None},
            {"name": "test", "date_added": None},
        ]

    def test_incorrect_field_in_fields_results_in_error(self, api_client):
        """Prove that adding invalid name to ?_fields will result in error"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        api_client.raise_request_exception = False
        response = api_client.get("/v1/movies", data={"_fields": "name,date"})
        data = read_response_json(response)

        assert response.status_code == 400, data
        assert data == {
            "type": "urn:apiexception:invalid",
            "title": "Invalid input.",
            "status": 400,
            "instance": "http://testserver/v1/movies?_fields=name%2Cdate",
            "invalid-params": [
                {
                    "type": "urn:apiexception:invalid:fields",
                    "name": "fields",
                    "reason": "'date' not among the available options",
                }
            ],
            "x-validation-errors": ["'date' not among the available options"],
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
        result = views.get_invalid_params(exception, exception.detail)
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
        result = views.get_invalid_params(exception, exception.detail)
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

    @staticmethod
    @pytest.mark.django_db
    def test_invalid_format(api_client, api_rf):
        """Prove that failed content negotiation still renders an error"""
        api_client.raise_request_exception = False
        response = api_client.get("/v1/movies", data={"_format": "jsonfdsfds"})
        assert response.status_code == 404
        assert response["content-type"] == "application/problem+json"  # check before reading
        data = read_response_json(response)

        # This 404 originates from DefaultContentNegotiation.filter_renderers()
        # Raising HTTP 406 Not Acceptable would only apply to HTTP Accept headers.
        assert data == {
            "detail": "Not found.",
            "status": 404,
            "title": "",
            "type": "urn:apiexception:not_found",
        }

    @staticmethod
    @pytest.mark.django_db
    def test_invalid_expand(api_client, api_rf):
        """Prove that _expand=some-field is properly rendered"""
        api_client.raise_request_exception = False
        response = api_client.get("/v1/movies", data={"_expand": "some-field"})
        assert response.status_code == 400
        assert response["content-type"] == "application/problem+json"  # check before reading
        data = read_response_json(response)

        assert data == {
            "type": "urn:apiexception:parse_error",
            "title": "Malformed request.",
            "detail": (
                "Only _expand=true is allowed. Use _expandScope to expand specific fields."
            ),
            "status": 400,
        }

    @staticmethod
    @pytest.mark.django_db
    def test_invalid_expand_scope(api_client, api_rf):
        """Prove that _expandScope=unknownField is properly rendered"""
        api_client.raise_request_exception = False
        response = api_client.get("/v1/movies", data={"_expandScope": "unknownField"})
        assert response.status_code == 400
        assert response["content-type"] == "application/problem+json"  # check before reading
        data = read_response_json(response)

        assert data == {
            "type": "urn:apiexception:parse_error",
            "title": "Malformed request.",
            "detail": (
                "Eager loading is not supported for field 'unknownField', "
                "available options are: actors, category"
            ),
            "status": 400,
        }

    @staticmethod
    @pytest.mark.django_db
    def test_extreme_page_size(api_client, api_rf):
        """Prove that the browser-based view protects against a DOS attack vector"""
        # First see that the API actually raises the exception
        with pytest.raises(ValidationError):
            api_client.get("/v1/movies", data={"_pageSize": "1001"}, HTTP_ACCEPT="text/html")

        # See that the 'handler500' of our local "urls.py" also kicks in.
        api_client.raise_request_exception = False
        response = api_client.get(
            "/v1/movies", data={"_pageSize": "1001"}, HTTP_ACCEPT="text/html"
        )

        assert response.status_code == ValidationError.status_code, response
        assert response["content-type"] == "application/problem+json"  # check before reading
        data = read_response_json(response)

        assert response["content-type"] == "application/problem+json"  # and after
        assert data == {
            "instance": "http://testserver/v1/movies?_pageSize=1001",
            "invalid-params": [
                {
                    "name": "_pageSize",
                    "reason": "Browsable HTML API does not support this page size.",
                    "type": "urn:apiexception:invalid:_pageSize",
                }
            ],
            "status": 400,
            "title": "Invalid input.",
            "type": "urn:apiexception:invalid",
            "x-validation-errors": ["Browsable HTML API does not support this page size."],
        }
