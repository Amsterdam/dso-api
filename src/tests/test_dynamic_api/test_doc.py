"""Tests for generated dataset documentation."""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse


@pytest.mark.django_db
def test_generic(api_client):
    """Quick test for the generic docs (Markdown rendering)."""
    index = reverse("dynamic_api:docs-generic", kwargs={"category": "rest", "topic": "index"})
    assert index

    response = api_client.get(index)
    assert response.status_code == 200


@pytest.mark.django_db
def test_overview(api_client, filled_router, fietspaaltjes_dataset):
    """Tests the documentation overview at /v1/docs."""
    overview = reverse("dynamic_api:docs-index")
    assert overview

    response = api_client.get(overview)
    assert response.status_code == 200

    content = response.rendered_content
    assert '<li><a href="generic/rest/filtering.html">Filtering</a></li>' in content
    assert '<a href="/v1/wfs/fietspaaltjes">WFS</a>' in content
    assert '<a href="/v1/mvt/fietspaaltjes">MVT</a>' in content
    assert '<a href="/v1/docs/datasets/fietspaaltjes.html">Documentatie</a>' in content
    assert "`" not in content  # Check for leftover ` from ReST-to-HTML conversion.


@pytest.mark.django_db
def test_dataset(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content

    # Check for self-link to wijken.
    assert """<a id="wijken" class="anchor">""" in content
    assert (
        """<a href="/v1/docs/datasets/gebieden.html#wijken">gebieden:wijken:ligtInStadsdeel</a>"""
        in content
    )

    # Check for field title
    assert "Object ID test title" in content

    # Check for publisher.
    # Disabled for now because of issues with schema loaders.
    # assert "<strong>Uitgever:</strong> Nobody" in content
    # assert "publisher/" not in content


@pytest.mark.django_db
def test_subresources_available_in_docs(api_client, gebieden_subresources_dataset, filled_router):
    """Assert that subresources are shown in the documentation for a dataset.

    The `gebieden_subresources` fixture has the following structure:
    - stadsdelen
        - wijken
            - buurten
    """
    url = reverse(
        "dynamic_api:docs-dataset",
        kwargs={"dataset_name": "gebieden_subresources"},
    )
    response = api_client.get(url)
    assert response.status_code == 200
    soup = BeautifulSoup(response.rendered_content, "html.parser")

    # Both stadsdelen and wijken should have a subresources tabel
    assert len(soup.find_all(string="Onderliggende tabellen")) == 2

    # Stadsdelen subresource lists both wijken and buurten.
    stadsdelen_subresources = (
        soup.find("table", id="stadsdelen-subresources").find("tbody").find_all("tr")
    )
    assert len(stadsdelen_subresources) == 2
    wijken = stadsdelen_subresources[0]
    assert wijken.find("a", href="#wijken").string == "wijken"
    wijken_url = "/v1/gebieden_subresources/stadsdelen/{stadsdelen_id}/wijken"
    assert wijken.find("a", href=wijken_url).string == wijken_url

    buurten = stadsdelen_subresources[1]
    assert buurten.find("a", href="#buurten").string == "buurten"
    buurten_url = "/v1/gebieden_subresources/stadsdelen/{stadsdelen_id}/wijken/{wijken_id}/buurten"
    assert buurten.find("a", href=buurten_url).string == buurten_url

    # Wijken subresource lists only buurten.
    wijken_subresources = soup.find("table", id="wijken-subresources").find("tbody").find_all("tr")
    assert len(wijken_subresources) == 1
    buurten = wijken_subresources[0]
    assert buurten.find("a", href="#buurten").string == "buurten"
    buurten_url = "/v1/gebieden_subresources/wijken/{wijken_id}/buurten"
    assert buurten.find("a", href=buurten_url).string == buurten_url


@pytest.mark.django_db
def test_table_for_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data/csv/gebieden_bouwblokken.csv.zip" in content
    assert "bulk-data/geojson/gebieden_bouwblokken.geojson.zip" in content

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content


@pytest.mark.django_db
def test_table_for_export_links_with_strict_auth_on_field(
    api_client, filled_router, gebieden_dataset
):
    """Tests documentation for a single dataset where one of the fields has an auth
    more strict than FP/MDW, resulting in regular download links"""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    field = table.fields.first()
    field.auth = "BRK/RS"
    field.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/" in content


@pytest.mark.django_db
def test_table_for_export_links_with_strict_auth_on_all_fields(
    api_client, filled_router, gebieden_dataset
):
    """Tests documentation for a single dataset where all the fields have an auth more
    strict than FP/MDW, resulting in no bulk downloads."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    for field in table.fields.all():
        field.auth = "BRK/RS"
        field.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/" not in content
    assert "bulk-data-fp-mdw/" not in content


@pytest.mark.django_db
def test_table_for_export_links_with_strict_auth_on_table(
    api_client, filled_router, gebieden_dataset
):
    """Tests documentation for a single dataset where the table has an auth more
    strict than FP/MDW, resulting in no bulk downloads."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.auth = "BRK/RS"
    table.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/" not in content
    assert "bulk-data-fp-mdw/" not in content


@pytest.mark.django_db
def test_table_for_export_links_with_strict_auth_on_dataset(
    api_client, filled_router, gebieden_dataset
):
    """Tests documentation for a single dataset with an auth more
    strict than FP/MDW, resulting in no bulk downloads."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    gebieden_dataset.auth = "BRK/RS"
    gebieden_dataset.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/" not in content
    assert "bulk-data-fp-mdw/" not in content


@pytest.mark.django_db
def test_table_for_confidential_dataset_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset with FP/MDW on the dataset."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    gebieden_dataset.auth = "FP/MDW"
    gebieden_dataset.save()

    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data-fp-mdw/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data-fp-mdw/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data-fp-mdw/csv/gebieden_bouwblokken.csv.zip" in content
    assert "bulk-data-fp-mdw/geojson/gebieden_bouwblokken.geojson.zip" in content


@pytest.mark.django_db
def test_table_for_confidential_table_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset with FP/MDW on the table."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.auth = "FP/MDW"
    table.enable_export = True
    table.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data-fp-mdw/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data-fp-mdw/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data-fp-mdw/csv/gebieden_bouwblokken.csv.zip" in content


@pytest.mark.django_db
def test_table_for_confidential_field_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset with FP/MDW on one field has both confidential and
    public links."""
    table = gebieden_dataset.tables.get(name="bouwblokken")
    table.enable_export = True
    table.save()
    field = table.fields.first()
    field.auth = "FP/MDW"
    field.save()
    # Gebieden has relationships between its tables.
    gebieden_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "gebieden"})
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "bulk-data/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data/csv/gebieden_bouwblokken.csv.zip" in content
    assert "bulk-data-fp-mdw/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data-fp-mdw/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data-fp-mdw/csv/gebieden_bouwblokken.csv.zip" in content


@pytest.mark.django_db
def test_dataset_casing(api_client, filled_router, hoofdroutes_dataset):
    """Tests documentation for dataset that needs camel casing."""
    hoofdroutes_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "hoofdroutes2"})
    assert hoofdroutes_doc

    response = api_client.get(hoofdroutes_doc)
    assert response.status_code == 200
    content = response.rendered_content

    assert """<a id="routesGevaarlijkeStoffen" class="anchor">""" in content
