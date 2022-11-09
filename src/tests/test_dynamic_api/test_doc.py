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


@pytest.mark.django_db
def test_dataset(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
    gebieden_doc = reverse("dynamic_api:doc-gebieden")  # Gebieden has relationships between its tables.
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content

    # Check for self-link to wijken.
    assert """<a id="wijken">""" in content
    assert """<a href="/v1/docs/datasets/gebieden.html#wijken">gebieden:wijken:ligtInStadsdeel</a>""" in content
