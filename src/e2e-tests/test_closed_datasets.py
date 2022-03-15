import os
from typing import cast

import pytest
import requests

# We get base urls from environment variables, providing defaults if those variables
# are not defined.
SCHEMA_URL = os.getenv("SCHEMA_URL", "https://acc.schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://acc.api.data.amsterdam.nl")
OIDC_TOKEN_ENDPOINT = os.getenv("OIDC_TOKEN_ENDPOINT")
DATADIENSTEN_TEST_CLIENT_ID = os.getenv("DATADIENSTEN_TEST_CLIENT_ID")
DATADIENSTEN_TEST_CLIENT_SECRET = os.getenv("DATADIENSTEN_TEST_CLIENT_SECRET")
# dataset_url = DATAPUNT_API_URL + "/v1/bor_inspecties/monitorbeeldkwaliteit/"
dataset_url = DATAPUNT_API_URL + "/v1/standvastgoed/gebouwen/"


@pytest.fixture(scope="session")
def auth_header():
    data = {
        "grant_type": "client_credentials",
        "client_id": DATADIENSTEN_TEST_CLIENT_ID,
        "client_secret": DATADIENSTEN_TEST_CLIENT_SECRET,
    }
    response = requests.post(cast(str, OIDC_TOKEN_ENDPOINT), data=data)
    response.raise_for_status()
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_collection_forbidden_without_credentials():
    """Prove that getting the collection is not accessible without credentials."""
    response = requests.get(dataset_url)
    assert response.status_code == 403


def test_collection_accessible_with_credentials(auth_header):
    """Prove that getting the collection is accessible with credentials."""
    response = requests.get(dataset_url, headers=auth_header)
    assert response.status_code == 200


def test_collection_with_query(auth_header):
    payload = {"pndId": "0363100012158535"}
    # payload = {"pandIdentificatie": "0363100012158535"}
    response = requests.get(dataset_url, headers=auth_header, json=payload)
    assert response.json()["_embedded"]["gebouwen"][0]["postcode"] == "1016GL"
