import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_overview(api_client, fietspaaltjes_dataset):
    """Tests the documentation overview at /v1/docs."""
    overview = reverse("dynamic_api:docs-index")
    assert overview

    response = api_client.get(overview)
    assert response.status_code == 200

    content = response.rendered_content
    assert """<a href="datasets/fietspaaltjes.html#fietspaaltjes">Fietspaaltjes</a>""" in content
