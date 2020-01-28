import pytest


@pytest.mark.django_db
def test_healthchecks(client):
    response = client.get("/status/health/")
    assert response.status_code in (200, 503)
