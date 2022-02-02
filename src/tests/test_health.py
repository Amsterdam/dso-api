import pytest


@pytest.mark.django_db
def test_healthchecks(client):
    response = client.get("/status/health/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_runtime_error(client):
    with pytest.raises(RuntimeError):
        client.get("/500-test/")


@pytest.mark.django_db
def test_runtime_error_status_code(client):
    client.raise_request_exception = False
    response = client.get("/500-test/")
    assert response.status_code == 500
