import json

import pytest
from django.db import connection
from django.urls import reverse

from dso_api.dbroles import DatabaseRoles

movie_data = {
    "_embedded": {
        "movie": [
            {
                "_links": {
                    "schema": "https://schemas.data.amsterdam.nl/datasets/movies/dataset#movie",
                    "self": {
                        "href": "http://testserver/v1/movies/movie/3",
                        "title": "foo123",
                        "id": 3,
                    },
                    "category": {
                        "href": "http://testserver/v1/movies/category/1",
                        "title": "bar",
                        "id": 1,
                    },
                    "actors": [],
                },
                "id": 3,
                "name": "foo123",
                "dateAdded": "2020-01-01T00:45:00",
                "enjoyable": None,
                "url": None,
                "categoryId": 1,
            },
            {
                "_links": {
                    "schema": "https://schemas.data.amsterdam.nl/datasets/movies/dataset#movie",
                    "self": {
                        "href": "http://testserver/v1/movies/movie/4",
                        "title": "test",
                        "id": 4,
                    },
                    "category": {
                        "href": "http://testserver/v1/movies/category/1",
                        "title": "bar",
                        "id": 1,
                    },
                    "actors": [],
                },
                "id": 4,
                "name": "test",
                "dateAdded": "2020-02-02T13:15:00",
                "enjoyable": None,
                "url": None,
                "categoryId": 1,
            },
        ]
    },
    "_links": {"self": {"href": "http://testserver/v1/movies/movie"}},
    "page": {"number": 1, "size": 20},
}

director_data = {
    "_embedded": {
        "director": [
            {
                "_links": {
                    "schema": "https://schemas.data.amsterdam.nl/datasets/movies/dataset#director",
                    "self": {
                        "href": "http://testserver/v1/movies/director/66",
                        "title": "Sjaak Fellini",
                        "id": 66,
                    },
                },
                "id": 66,
                "name": "Sjaak Fellini",
            }
        ]
    },
    "_links": {"self": {"href": "http://testserver/v1/movies/director"}},
    "page": {"number": 1, "size": 20},
}


@pytest.mark.django_db
def test_anonymous_when_no_token(filled_router, api_client, activate_dbroles, settings):
    url = reverse("dynamic_api:movies-movie-list")
    response = api_client.get(url)
    assert response.status_code == 200
    assert DatabaseRoles._get_end_user() == DatabaseRoles.ANONYMOUS

    # The user context is terminated when content is streamed so we
    # can make assertions about the session state here
    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.ANONYMOUS_ROLE

    # Anonymous users can see movies
    assert json.loads("".join([x.decode() for x in response.streaming_content])) == movie_data
    # Ensure the connection session context is cleaned up
    assert DatabaseRoles._get_role(connection) is None
    assert DatabaseRoles._get_end_user() is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER


@pytest.mark.django_db
def test_user_when_token(
    filled_router,
    api_client,
    activate_dbroles,
    fetch_auth_token,
    settings,
):
    url = reverse("dynamic_api:movies-director-list")
    token = fetch_auth_token(["TEST_OPENBAAR", "TEST_DIRECTOR"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert DatabaseRoles._get_end_user() == settings.TEST_USER_EMAIL

    # The user context is terminated when content is streamed so we
    # can make assertions about the session state here
    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == f"{settings.TEST_USER_EMAIL}_role"

    # The test user can see directors and movie data
    assert json.loads("".join([x.decode() for x in response.streaming_content])) == director_data
    # Ensure the connection session context is cleaned up
    assert DatabaseRoles._get_role(connection) is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER


@pytest.mark.django_db
def test_user_switches_on_consecutive_requests(
    filled_router,
    api_client,
    activate_dbroles,
    fetch_auth_token,
    settings,
):
    url = reverse("dynamic_api:movies-director-list")
    token = fetch_auth_token(["TEST_OPENBAAR", "TEST_DIRECTOR"])
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert DatabaseRoles._get_end_user() == settings.TEST_USER_EMAIL

    # The user context is terminated when content is streamed so we
    # can make assertions about the session state here
    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == f"{settings.TEST_USER_EMAIL}_role"

    # The test user can see directors and movie data
    assert json.loads("".join([x.decode() for x in response.streaming_content])) == director_data
    # Ensure the connection session context is cleaned up
    assert DatabaseRoles._get_role(connection) is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER

    url = reverse("dynamic_api:movies-movie-list")
    response = api_client.get(url)
    assert response.status_code == 200
    assert DatabaseRoles._get_end_user() == "ANONYMOUS"

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.ANONYMOUS_ROLE

    # Anonymous users can see movies
    assert json.loads("".join([x.decode() for x in response.streaming_content])) == movie_data
    # Ensure the connection session context is cleaned up
    assert DatabaseRoles._get_role(connection) is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER


@pytest.mark.django_db
def test_internal_user_when_subject_without_role(
    filled_router,
    api_client,
    activate_dbroles,
    fetch_auth_token,
    settings,
):
    url = reverse("dynamic_api:movies-movie-list")
    email = "harry@amsterdam.nl"
    token = fetch_auth_token(["TEST_OPENBAAR"], email)
    response = api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert DatabaseRoles._get_end_user() == email

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.INTERNAL_ROLE

    # The internal user can see movie data
    assert json.loads("".join([x.decode() for x in response.streaming_content])) == movie_data

    # Ensure the connection session context is cleaned up
    assert DatabaseRoles._get_role(connection) is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER


@pytest.mark.django_db
def test_permission_error_for_external_unknown_users(
    filled_router,
    api_client,
    activate_dbroles,
    fetch_auth_token,
    settings,
):
    url = reverse("dynamic_api:movies-movie-list")
    email = "harry@rotterdam.nl"
    token = fetch_auth_token(["TEST_OPENBAAR"], email)

    with pytest.raises(PermissionError):
        api_client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    assert DatabaseRoles._get_role(connection) is None

    with connection.cursor() as c:
        c.execute("SELECT current_user;")
        assert c.fetchone()[0] == settings.DB_USER
