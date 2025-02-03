"""Tests for generated dataset documentation."""

import re

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
    assert (
        """<a href="/v1/docs/datasets/fietspaaltjes.html#fietspaaltjes">Fietspaaltjes</a>"""
        in content
    )
    assert "`" not in content  # Check for leftover ` from ReST-to-HTML conversion.


@pytest.mark.django_db
def test_dataset(api_client, filled_router, gebieden_dataset):
    """Tests documentation for a single dataset."""
    gebieden_doc = reverse(
        "dynamic_api:doc-gebieden"
    )  # Gebieden has relationships between its tables.
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content

    # Check for self-link to wijken.
    assert """<a id="wijken">""" in content
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
    table = gebieden_dataset.tables.get(name='bouwblokken')
    table.enable_export = True
    table.save()
    gebieden_doc = reverse(
        "dynamic_api:doc-gebieden"
    )  # Gebieden has relationships between its tables.
    assert gebieden_doc

    response = api_client.get(gebieden_doc)
    assert response.status_code == 200
    content = response.rendered_content
    # Extensions for exported format followed by ".zip"
    # are signalling links to the generated exports.
    assert "gebieden_bouwblokken.gpkg.zip" in content
    assert "gebieden_bouwblokken.jsonl.zip" in content
    assert "gebieden_bouwblokken.csv.zip" in content

    assert "gebieden_buurten.csv.zip" not in content
    assert "gebieden_buurten.jsonl.zip" not in content
    assert "gebieden_buurten.gpkg.zip" not in content

@pytest.mark.django_db
def test_dataset_casing(api_client, filled_router, hoofdroutes_dataset):
    """Tests documentation for dataset that needs camel casing."""
    hoofdroutes_doc = reverse("dynamic_api:doc-hoofdroutes2")
    assert hoofdroutes_doc

    response = api_client.get(hoofdroutes_doc)
    assert response.status_code == 200
    content = response.rendered_content

    assert """<a id="routesGevaarlijkeStoffen">""" in content


@pytest.mark.django_db
def test_wfs_dataset(api_client, filled_router, fietspaaltjes_dataset):
    """Assert that fietspaaltjes has WFS docs."""
    fietspaaltjes_doc = reverse("dynamic_api:doc-wfs-fietspaaltjes")
    assert fietspaaltjes_doc

    response = api_client.get(fietspaaltjes_doc)
    assert response.status_code == 200
    content = response.rendered_content

    # Check for the CSV and GeoJSON download links.
    assert re.search(
        r"""CSV.export:.*href="/v1/wfs/fietspaaltjes.*OUTPUTFORMAT=CSV""", content, re.I
    )
    assert re.search(
        r"""GeoJSON.export:.*href="/v1/wfs/fietspaaltjes.*OUTPUTFORMAT=geojson""",
        content,
        re.I,
    )
