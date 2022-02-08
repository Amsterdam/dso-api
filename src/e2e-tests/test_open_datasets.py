import os

import requests

# We get base urls from environment variables, providing defaults if those variables
# are not defined.
SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://api.data.amsterdam.nl")
dataset_url = DATAPUNT_API_URL + "/v1/aardgasvrijezones/buurt/"


def test_collection_succes():
    """Prove that getting the collection resources succeeds."""
    response = requests.get(dataset_url)
    assert response.status_code == 200


def test_not_found():
    """Prove that providing a non-existing resource id results in a 404."""
    # Just use an arbitrary high number
    response = requests.get(dataset_url + "9999999")
    assert response.status_code == 404


def test_record_succes():
    """Prove that getting one resources succeeds and has expected content."""
    response = requests.get(dataset_url + "17/")
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == 17
    assert content["buurtNaam"] == "Holysloot"


def test_query_by_id():
    """Prove that query-ing by `id` finds expected resource."""
    payload = {"id": 16}
    response = requests.get(dataset_url, params=payload)
    assert response.status_code == 200
    content = response.json()
    records = content["_embedded"]["buurt"]
    assert len(records) == 1
    assert records[0]["id"] == 16
    assert records[0]["buurtNaam"] == "Ransdorp"


def test_providing_wrongly_types_query():
    """Prove that providing a string where an int is expected results in 400 (Bad Request)."""
    payload = {"id": "foo"}
    response = requests.get(dataset_url, params=payload)
    assert response.status_code == 400


def test_query_using_like():
    """Prove that a `like` query using a wildcard finds the expected resource."""
    payload = {"buurtNaam[like]": "*Gool"}
    response = requests.get(dataset_url, params=payload)
    assert response.status_code == 200
    content = response.json()
    records = content["_embedded"]["buurt"]
    assert len(records) == 1
    assert records[0]["id"] == 4
    assert records[0]["buurtCode"] == "BU03636910"
