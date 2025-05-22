import pytest
from django.contrib.gis.geos import Point
from django.db import connection
from django.urls import path
from rest_framework import generics, viewsets
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.routers import SimpleRouter

from rest_framework_dso import views
from rest_framework_dso.renderers import HALJSONRenderer
from tests.utils import read_response, read_response_json, read_response_partial

from .models import Location, Movie
from .serializers import LocationSerializer, MovieSerializer


class MovieDetailAPIView(views.DSOViewMixin, generics.RetrieveAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class MovieListAPIView(views.DSOViewMixin, generics.ListAPIView):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class MovieViewSet(views.DSOViewMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = MovieSerializer
    queryset = Movie.objects.all()


class LocationListAPIView(views.DSOViewMixin, generics.ListAPIView):
    serializer_class = LocationSerializer
    queryset = Location.objects.all()


router = SimpleRouter(trailing_slash=False)
router.register("v1/viewset/movies", MovieViewSet, basename="viewset-movies")

urlpatterns = [
    path("v1/locations", LocationListAPIView.as_view(), name="locations-list"),
    path("v1/movies", MovieListAPIView.as_view(), name="movies-list"),
    path("v1/movies/<pk>", MovieDetailAPIView.as_view(), name="movies-detail"),
] + router.get_urls()

handler500 = views.server_error

pytestmark = [pytest.mark.urls(__name__)]  # enable for all tests in this file


@pytest.mark.django_db
class TestExpand:
    @pytest.mark.parametrize(
        "params",
        [
            {"_expand": "true"},
            # Variations that should give the same effect:
            {
                "_expand": "true",
                "_expandScope": "actors.last_updated_by,category.last_updated_by",
            },
            {
                "_expand": "true",
                "_expandScope": "actors,actors.last_updated_by,category,category.last_updated_by",
            },
        ],
    )
    def test_detail_expand_nested(self, api_client, movie, params):
        """Prove that ?_expand=true expands everything recursively.
        The second time, params defines all expanded objects which should give the same response.
        """
        response = api_client.get(f"/v1/movies/{movie.pk}", data=params)
        data = read_response_json(response)
        assert data == {
            "name": "foo123",
            "category_id": movie.category_id,
            "date_added": None,
            "_embedded": {
                "actors": [
                    {
                        "name": "Jane Doe",
                        "_embedded": {"last_updated_by": {"name": "jane_updater"}},
                    },
                    {
                        "name": "John Doe",
                        "_embedded": {"last_updated_by": None},
                    },
                ],
                "category": {
                    "name": "bar",
                    "_embedded": {"last_updated_by": {"name": "bar_man"}},
                },
            },
        }
        assert response["Content-Type"] == "application/hal+json"

    @pytest.mark.parametrize(
        "params",
        [
            {"_expand": "true", "_expandScope": "actors,category"},
            {"_expandScope": "actors,category"},  # backwards compatibility
        ],
    )
    def test_detail_expand_scope(self, api_client, movie, params):
        """Prove that ?_expandScope works fine for a single level.
        Nesting also doesn't go deeper here.
        """
        response = api_client.get(f"/v1/movies/{movie.pk}", data=params)
        data = read_response_json(response)
        assert data == {
            "name": "foo123",
            "category_id": movie.category_id,
            "date_added": None,
            "_embedded": {
                "actors": [
                    {"name": "Jane Doe"},
                    {"name": "John Doe"},
                ],
                "category": {"name": "bar"},
            },
        }
        assert response["Content-Type"] == "application/hal+json"

    @pytest.mark.parametrize(
        "params",
        [
            {"_expand": "false"},
            {"_expand": "false", "_expandScope": "actors,category"},
        ],
    )
    def test_detail_expand_false(self, api_client, movie, params):
        """Prove that ?_expand=false doesn't trigger expansion."""
        response = api_client.get(f"/v1/movies/{movie.pk}", data=params)
        data = read_response_json(response)
        assert data == {
            "name": "foo123",
            "category_id": movie.category_id,
            "date_added": None,
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

    @staticmethod
    @pytest.mark.parametrize("category_id", [None, 9999999])
    def test_detail_expand_nulls(api_client, category_id):
        """Prove that expanding NULL values or invalid FK values won't crash.
        The _embedded part has a None value instead.
        """
        movie = Movie.objects.create(name="foo123", category_id=category_id)
        try:
            response = api_client.get(
                f"/v1/movies/{movie.pk}", data={"_expandScope": "actors,category"}
            )
            data = read_response_json(response)
            assert data == {
                "name": "foo123",
                "category_id": category_id,
                "date_added": None,
                "_embedded": {
                    "actors": [],
                    "category": None,
                },
            }
            assert response["Content-Type"] == "application/hal+json"
        finally:
            # avoid Fk constraint errors when constraints are checked before rollback
            movie.delete()

    def test_list_expand_true(self, api_client, movie):
        """Prove that ?_expand both work for the list view."""
        response = api_client.get("/v1/movies", data={"_expand": "true"})
        data = read_response_json(response)
        assert data == {
            "_links": {
                "self": {"href": "http://testserver/v1/movies?_expand=true"},
            },
            "_embedded": {
                "movie": [
                    {"name": "foo123", "category_id": movie.category_id, "date_added": None}
                ],
                "actors": [
                    {
                        "name": "Jane Doe",
                        "_embedded": {"last_updated_by": {"name": "jane_updater"}},
                    },
                    {
                        "name": "John Doe",
                        "_embedded": {"last_updated_by": None},
                    },
                ],
                "category": [
                    {
                        "name": "bar",
                        "_embedded": {"last_updated_by": {"name": "bar_man"}},
                    }
                ],
            },
            "page": {"number": 1, "size": 20},
        }
        assert response["Content-Type"] == "application/hal+json"

    @pytest.mark.parametrize(
        "params",
        [
            {"_expand": "true", "_expandScope": "actors,category"},
            {"_expandScope": "actors,category"},  # backwards compatibility
        ],
    )
    def test_list_expand_scope(self, api_client, movie, params):
        """Prove that ?_expand=true and ?_expandScope=category both work for the detail view.
        This also tests the parameter expansion within the view logic.
        """
        response = api_client.get("/v1/movies", data=params)
        data = read_response_json(response)
        assert data == {
            "_links": {
                "self": {
                    "href": f"http://testserver/v1/movies?{response.request['QUERY_STRING']}"
                },
            },
            "_embedded": {
                "movie": [
                    {"name": "foo123", "category_id": movie.category_id, "date_added": None}
                ],
                "actors": [
                    {"name": "Jane Doe"},
                    {"name": "John Doe"},
                ],
                "category": [{"name": "bar"}],
            },
            "page": {"number": 1, "size": 20},
        }
        assert response["Content-Type"] == "application/hal+json"

    @pytest.mark.parametrize(
        "params",
        [
            {"_expand": "false"},
            {"_expand": "false", "_expandScope": "actors,category"},
        ],
    )
    def test_list_expand_false(self, api_client, movie, params):
        """Prove that ?_expand=false won't trigger expansion."""
        response = api_client.get("/v1/movies", data=params)
        data = read_response_json(response)
        assert data == {
            "_links": {
                "self": {
                    "href": f"http://testserver/v1/movies?{response.request['QUERY_STRING']}"
                },
            },
            "_embedded": {
                "movie": [
                    {"name": "foo123", "category_id": movie.category_id, "date_added": None}
                ],
            },
            "page": {"number": 1, "size": 20},
        }
        assert response["Content-Type"] == "application/hal+json"


@pytest.mark.django_db
class TestBrowsableAPIRenderer:
    """Test the HTML view"""

    def test_list_expand_api(self, api_client, movie):
        """Prove that the browsable API returns HTML."""
        response = api_client.get("/v1/movies", data={"_expand": "true"}, HTTP_ACCEPT="text/html")
        assert response["content-type"] == "text/html; charset=utf-8"
        read_response(response)  # Runs template rendering

    @pytest.mark.parametrize(
        ["base_url", "expect"],
        [
            ("/v1/movies", "Movie Detail Api"),  # regular APIView, can't detect request type
            ("/v1/viewset/movies", "foo123"),  # ViewSet, can inspect request type and response
        ],
    )
    def test_detail_title_fields(self, api_client, movie, base_url, expect):
        """Prove that get_view_name() works for regular API views."""
        response = api_client.get(
            f"{base_url}/{movie.pk}", data={"_fields": "name"}, HTTP_ACCEPT="text/html"
        )
        assert response.status_code == 200, response
        assert response["content-type"] == "text/html; charset=utf-8"
        html = read_response(response)
        title = next(line.strip() for line in html.splitlines() if "<h1>" in line)
        assert title == f"<h1>{expect}</h1>"


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
        assert data["_embedded"] == {
            "movie": [
                {"name": "foo123"},
                {"name": "test"},
            ]
        }

    def test_limit_multiple_fields(self, api_client):
        """Prove that ?_fields=name,date results in result with only names and dates"""
        Movie.objects.create(name="test")
        Movie.objects.create(name="foo123")

        response = api_client.get("/v1/movies", data={"_fields": "name,date_added"})
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "movie": [
                {"name": "foo123", "date_added": None},
                {"name": "test", "date_added": None},
            ]
        }

    def test_limit_expanded_field(self, api_client, movie):
        """Prove that ?_fields=name results in result with only names"""
        response = api_client.get(
            "/v1/movies",
            data={
                "_fields": "name,category.name,category.last_updated_by.name",
                "_expandScope": "category.last_updated_by",
            },
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "movie": [
                {"name": "foo123"},
            ],
            "category": [
                {
                    "name": "bar",
                    "_embedded": {
                        "last_updated_by": {"name": "bar_man"},
                    },
                },
            ],
        }

    def test_limit_expanded_field_exclude(self, api_client, movie):
        """Prove that excluding a subfield still gives the whole main object."""
        response = api_client.get(
            "/v1/movies",
            data={
                "_fields": "-category.last_updated_by.name",
                "_expandScope": "category.last_updated_by",
            },
        )
        data = read_response_json(response)
        assert response.status_code == 200, data
        assert data["_embedded"] == {
            "movie": [
                # Still complete movie:
                {"category_id": 1, "date_added": None, "name": "foo123"},
            ],
            "category": [
                {
                    "name": "bar",
                    "_embedded": {
                        "last_updated_by": {},  # removed name (the only field)
                    },
                }
            ],
        }

    def test_incorrect_field_in_fields_results_in_error(self, api_client):
        """Prove that adding invalid name to ?_fields will result in error"""
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
                    "reason": "The following field name is invalid: 'date'.",
                }
            ],
            "x-validation-errors": ["The following field name is invalid: 'date'."],
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
                "Only _expand=true|false is allowed. Use _expandScope to expand specific fields."
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
    def test_coordinate_conversion_fail(api_client, api_rf):
        """Prove that some errors will be properly displayed as human readable.

        The test run causes an error in the first record, which is examined before
        the streaming starts. This triggers the standard exception handler.
        """
        with connection.cursor() as c:
            # Create an "POINT(Infinity Infinity)" coordinate without triggering
            # any validations at Python-level.
            c.execute(
                f"INSERT INTO {Location._meta.db_table} (id, geometry) VALUES (1, %s)",
                ("010100002040710000000000000000F07F000000000000F07F",),
            )

        response = api_client.get("/v1/locations", HTTP_ACCEPT_CRS="EPSG:4258")
        data = read_response_json(response)
        assert response["content-type"] == "application/problem+json", data  # check before reading
        assert data == {
            "detail": (
                "Fout tijdens coördinaatconversie voor location #1. Neem a.u.b. "
                "contact op met de bronhouder van deze data om dit probleem op te lossen."
            ),
            "instance": "http://testserver/v1/locations",
            "status": 500,
            "title": "Coordinate conversion failed",
            "type": "urn:apiexception:error",
        }

    @staticmethod
    @pytest.mark.django_db
    def test_coordinate_conversion_fail_streaming(api_client, api_rf, monkeypatch):
        """Prove that some errors will be properly displayed as human readable.

        This test variation triggers an error while the streaming output is already
        being sent. This triggers a different exception handling during the rendering.
        """
        Location.objects.create(id=1, geometry=Point(155000, 463000))
        with connection.cursor() as c:
            # Create an "POINT(Infinity Infinity)" coordinate without triggering
            # any validations at Python-level.
            c.execute(
                f"INSERT INTO {Location._meta.db_table} (id, geometry) VALUES (2, %s)",
                ("010100002040710000000000000000F07F000000000000F07F",),
            )

        # Force quick streaming, and error handling.
        monkeypatch.setattr(HALJSONRenderer, "chunk_size", 1)
        api_client.raise_request_exception = False

        response = api_client.get("/v1/locations", HTTP_ACCEPT_CRS="EPSG:4258")
        data, exception = read_response_partial(response)
        assert exception is not None
        assert response["content-type"] == "application/hal+json", data  # standard response
        assert data.startswith(
            "{\n"
            '  "_embedded":{\n'
            '  "location":[\n'
            '  {"geometry":{"type":"Point","coordinates":[5'  # don't care for exact coordinate
        ), data
        assert data.endswith(
            "]}}"
            "/* Aborted by GDALException: Fout tijdens coördinaatconversie voor location #2."
            " Neem a.u.b. contact op met de bronhouder van deze data om dit probleem op te lossen."
            " */\n"
        ), data

    @staticmethod
    @pytest.mark.django_db
    def test_pagination_beyond_last_page(api_client):
        """Prove that going beyond the last page gives a 404."""
        response_page_1 = api_client.get("/v1/movies", data={"page": 1})
        data = read_response_json(response_page_1)
        assert response_page_1.status_code == 200, data  # empty page
        assert data == {
            "_embedded": {"movie": []},
            "_links": {"self": {"href": "http://testserver/v1/movies?page=1"}},
            "page": {"number": 1, "size": 20},
        }

        response_page_2 = api_client.get("/v1/movies", data={"page": 2})
        data = read_response_json(response_page_2)
        assert response_page_2.status_code == 404, data  # not existent
        assert data == {
            "detail": "Invalid page.",
            "status": 404,
            "title": "Not found.",
            "type": "urn:apiexception:not_found",
        }


@pytest.mark.django_db
class TestListCount:
    @pytest.mark.parametrize("page_size_param", ["_pageSize", "page_size"])
    def test_list_count_included(self, page_size_param, api_client):
        Movie.objects.create(name="foo123")
        Movie.objects.create(name="test")

        response = api_client.get("/v1/movies", data={"_count": "true"})
        data = read_response_json(response)
        assert response.status_code == 200
        assert response["X-Total-Count"] == "2"
        assert data["page"]["totalElements"] == 2
        assert response["X-Pagination-Count"] == "1"
        assert data["page"]["totalPages"] == 1

        Movie.objects.create(name="bla")

        response = api_client.get("/v1/movies", data={"_count": "true", page_size_param: 2})
        assert response.status_code == 200
        data = read_response_json(response)
        assert response["X-Total-Count"] == "3"
        assert data["page"]["totalElements"] == 3
        assert response["X-Pagination-Count"] == "2"
        assert data["page"]["totalPages"] == 2

    @pytest.mark.parametrize("data", [{}, {"_count": "false"}, {"_count": "0"}, {"_count": "1"}])
    def test_list_count_excluded(self, api_client, django_assert_num_queries, data):
        Movie.objects.create(name="foo123")
        Movie.objects.create(name="test")

        with django_assert_num_queries(2) as captured:
            response = api_client.get("/v1/movies", data=data)

        # Make sure we are not inadvertently executing a COUNT
        assert all("COUNT" not in q["sql"] for q in captured.captured_queries)

        data = read_response_json(response)
        assert response.status_code == 200
        assert "X-Total-Count" not in response
        assert "X-Pagination-Count" not in response
        assert "totalElements" not in data["page"]
        assert "totalPages" not in data["page"]

    # Test that all object are returned during pagination
    @pytest.mark.parametrize("page_size_param", ["_pageSize", "page_size"])
    def test_list_pagination(self, page_size_param, api_client):
        movie_objects = {"foo", "bar", "baz", "xyz"}
        for movie in movie_objects:
            Movie.objects.create(name=movie)

        response_page_1 = api_client.get(
            "/v1/movies", data={"_count": "true", page_size_param: 2, "page": 1}
        )
        response_page_2 = api_client.get(
            "/v1/movies", data={"_count": "true", page_size_param: 2, "page": 2}
        )
        movies_returned = [
            movie["name"]
            for movie in read_response_json(response_page_1)["_embedded"]["movie"]
            + read_response_json(response_page_2)["_embedded"]["movie"]
        ]

        assert set(movies_returned) == movie_objects
