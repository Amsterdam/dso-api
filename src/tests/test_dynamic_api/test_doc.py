"""Tests for generated dataset documentation."""

import pytest
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

    # Check for publisher.
    # Disabled for now because of issues with schema loaders.
    # assert "<strong>Uitgever:</strong> Nobody" in content
    # assert "publisher/" not in content


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

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content


@pytest.mark.django_db
def test_table_for_confidential_dataset_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
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

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content


@pytest.mark.django_db
def test_table_for_confidential_table_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
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

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content


@pytest.mark.django_db
def test_table_for_confidential_field_export_links(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
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
    assert "bulk-data-fp-mdw/geopackage/gebieden_bouwblokken.gpkg.zip" in content
    assert "bulk-data-fp-mdw/jsonlines/gebieden_bouwblokken.jsonl.zip" in content
    assert "bulk-data-fp-mdw/csv/gebieden_bouwblokken.csv.zip" in content

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content


@pytest.mark.django_db
def test_dataset_casing(api_client, filled_router, hoofdroutes_dataset):
    """Tests documentation for dataset that needs camel casing."""
    hoofdroutes_doc = reverse("dynamic_api:docs-dataset", kwargs={"dataset_name": "hoofdroutes2"})
    assert hoofdroutes_doc

    response = api_client.get(hoofdroutes_doc)
    assert response.status_code == 200
    content = response.rendered_content

    assert """<a id="routesGevaarlijkeStoffen" class="anchor">""" in content
