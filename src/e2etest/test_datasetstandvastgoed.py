# Validate String date format
# Using strptime()
from datetime import datetime
from typing import cast

import allure
import pytest
import requests

from . import dataconstantstandvastgoed


@pytest.fixture(scope="session")
def auth_header():
    data = {
        "grant_type": "client_credentials",
        "client_id": dataconstantstandvastgoed.DATADIENSTEN_TEST_CLIENT_ID,
        "client_secret": dataconstantstandvastgoed.DATADIENSTEN_TEST_CLIENT_SECRET,
    }
    response = requests.post(cast(str, dataconstantstandvastgoed.OIDC_TOKEN_ENDPOINT), data=data)
    response.raise_for_status()
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_collection_accessible_with_credentials(auth_header):

    """Prove that getting the collection is accessible with credentials."""
    response = requests.get(dataconstantstandvastgoed.dataset_url, headers=auth_header)
    assert response.status_code == 200, "Status code not match"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/id=2022-01-01.0363200000205917.3` to check the existing property"
)
def test_query_existinggebouwen(auth_header):

    """Prove that query-ing by `id` finds property."""

    payload = {"id": "2022-01-01.0363200000205917.3"}
    response = requests.get(
        dataconstantstandvastgoed.dataset_url, params=payload, headers=auth_header
    )
    content = response.json()
    records = content["_embedded"]["gebouwen"]
    assert len(records) == 1
    assert records[0]["naam"] == "Molenpad"
    assert records[0]["postcode"] == "1016GL"
    assert records[0]["gmeNaam"] == "Amsterdam"
    assert records[0]["pndId"] == "0363100012174763"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/id=2022-01-01.0363200000205917.3` to check the existing property"
)
def test_query_naamgebouwen(auth_header):

    """Prove that query-ing by `id` finds property."""

    payload = {"gmeNaam[like]": "*dam"}
    response = requests.get(
        dataconstantstandvastgoed.dataset_url, params=payload, headers=auth_header
    )
    content = response.json()
    records = content["_embedded"]["gebouwen"]
    assert len(records) == 1
    assert records[0]["naam"] == "Molenpad"
    assert records[0]["postcode"] == "1016GL"
    assert records[0]["gmeNaam"] == "Amsterdam"
    assert records[0]["pndId"] == "0363100012174763"


@allure.step(
    "Validate `aotRegistratiedatum` format as `datetime` for the API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/id=2022-01-01.0363200000205917.3`"
)
def test_datetime_validation(auth_header):

    """Proving the datetime for `aotRegistratiedatum`"""

    payload = {"id": "2022-01-01.0363200000205917.3"}
    response = requests.get(
        dataconstantstandvastgoed.dataset_url, params=payload, headers=auth_header
    )
    content = response.json()
    records = content["_embedded"]["gebouwen"]
    aotRegistratiedatum = records[0]["aotRegistratiedatum"]
    # initializing format
    format = "%Y-%m-%dT%H:%M:%S"
    # checking if format matches the date
    res = True

    # using try-except to check for truth value
    try:
        res = bool(datetime.strptime(aotRegistratiedatum, format))
    except ValueError:
        res = False

    assert str(res) == "True"


@allure.step(
    "Validate `standBegingeldigheid` format as `date` for the API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/id=2022-01-01.0363200000205917.3`"
)
def test_date_validation(auth_header):

    """Proving the datetime for `standBegingeldigheid`"""

    payload = {"id": "2022-01-01.0363200000205917.3"}
    response = requests.get(
        dataconstantstandvastgoed.dataset_url, params=payload, headers=auth_header
    )
    content = response.json()
    records = content["_embedded"]["gebouwen"]
    standBegingeldigheid = records[0]["standBegingeldigheid"]
    # initializing format
    format = "%Y-%m-%dT%H:%M:%S"
    # checking if format matches the date
    res = True

    # using try-except to check for truth value
    try:
        res = bool(datetime.strptime(standBegingeldigheid, format))
    except ValueError:
        res = False

    assert str(res) == "False"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/` to validate whether the no record found with `failure code 403`"
)
def test_collection_forbidden_without_credentials():

    """Prove that getting the collection is not accessible without credentials."""
    response = requests.get(dataconstantstandvastgoed.dataset_url)
    assert response.status_code == 403, "Status code not match"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/standvastgoed/gebouwen/2022-01-01.03632000002059CC/?nummeraanduidingVolgnummer=3` to validate whether the no record found with `failure code 404`"
)
def test_collection_notfound_with_credendtials(auth_header):

    """Prove that getting the collection is not found without credentials."""
    response = requests.get(dataconstantstandvastgoed.dataset_url_parameter, headers=auth_header)
    assert response.status_code == 404, "Status code not match"
