from queue import Empty

import allure
import pytest
import requests
from sqlalchemy import null

from . import datasetconstant, datasetconstantinit


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/` match to `success code 200`"
)
def test_buurtid_success():

    """Success API request for Natural gas-free neighborhoods"""

    buurtidresp = requests.get(datasetconstant.dataset_url + "475")
    assert buurtidresp.status_code == 200, "Status code not match"


@allure.step(
    "Validate the Buurt name should not be empty for an id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/475`"
)
def test_buurtnaam_queryparam():

    """Buurt Naame Query Parameter Validation for the Natural gas-free Neighborhoods"""

    buurtidresp = requests.get(datasetconstant.dataset_url + "475")
    buurtid_response = buurtidresp.json()

    if buurtid_response["buurtNaam"] is Empty:
        assert buurtid_response["buurtNaam"] == ""
    else:
        assert buurtid_response["buurtNaam"] != ""

    assert datasetconstant.buurtname in buurtid_response["buurtNaam"]


@allure.step(
    "Validate the Buurt code should not be null for an id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/475`"
)
def test_buurtid_queryparam():

    """Buurt code Query Parameter Validation for the Natural gas-free Neighborhoods"""

    buurtidresp = requests.get(datasetconstant.dataset_url + "475")
    buurtid_response = buurtidresp.json()

    if buurtid_response["buurtCode"] is null:
        assert buurtid_response["buurtCode"] is None
    else:
        assert buurtid_response["buurtCode"] is not None


@allure.step(
    "Validate the Geometry coordinates for an id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/475`"
)
def test_geometry_queryparam():

    """Geometry Query Parameter Validation for the Natural gas-free Neighborhoods"""

    buurtidresp = requests.get(datasetconstant.dataset_url + "475")
    buurtid_response = buurtidresp.json()

    assert buurtid_response["geometry"]["coordinates"][0][0][0] == datasetconstant.coordinate


@allure.step(
    "Validate the Aandeelkookgas have null for an id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/475`"
)
def test_cookinggas_queryparam():

    """Share Cooking Gas Query Parameter Validation for the Natural gas-free Neighborhoods"""

    buurtidresp = requests.get(datasetconstant.dataset_url + "475")
    buurtid_response = buurtidresp.json()

    if buurtid_response["aandeelKookgas"] is None:
        assert buurtid_response["aandeelKookgas"] is None
    else:
        assert buurtid_response["aandeelKookgas"] is not None


@allure.step(
    "Querying the records greater than 16 for the API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/?id[gte]=16`"
)
def test_query_by_id():

    """Prove that query-ing by `id` finds expected resource."""

    payload = {"id[gte]": 16}
    buurtidresp = requests.get(datasetconstant.dataset_url, params=payload)
    content = buurtidresp.json()
    records = content["_embedded"]["buurt"]
    assert len(records) > 1
    assert records[0]["id"] == 16


@allure.step(
    "Querying the records for buurtname end like `*Gool` for the API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/?buurtNaam[like]=*Gool`"
)
def test_query_using_like():

    """Prove that a `like` query using a wildcard finds the expected resource."""

    payload = {"buurtNaam[like]": "*Gool"}
    buurtidresp = requests.get(datasetconstant.dataset_url, params=payload)
    content = buurtidresp.json()
    records = content["_embedded"]["buurt"]
    assert len(records) == 1
    assert records[0]["id"] == 4
    assert records[0]["buurtCode"] == "BU03636910"


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurt/?id=foo` match to `Bad request code 400`"
)
def test_providing_wrongly_types_query():

    """Prove that providing a string where an int is expected results in 400 (Bad Request)."""

    payload = {"id": "foo"}
    buurtidresp = requests.get(datasetconstant.dataset_url, params=payload)
    assert buurtidresp.status_code == 400


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/` match to `success code 200`"
)
def test_buurtinitiatiefid_success():

    """Success API request for Natural gas-free neighborhoods initiatives"""

    buurtinitiatiefidresp = requests.get(datasetconstantinit.dataset_url)
    assert buurtinitiatiefidresp.status_code == 200, "Status code not match"


@allure.step(
    "Validate the id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/50` match in the json response for the id value"
)
def test_buurtinitiatiefid_queryparam():

    """Buurt id Query Parameter Validation for the Natural gas-free Neighborhoods initiatives"""

    buurtinitiatiefidresp = requests.get(datasetconstantinit.dataset_url + "50")
    buurtinitiatiefid_response = buurtinitiatiefidresp.json()

    assert (
        int((datasetconstantinit.dataset_url + "50").split("/")[-1])
        == buurtinitiatiefid_response["id"]
    )


@allure.step(
    "Validate the Buurt name should not be empty for an id in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/50`"
)
def test_buurtnameinitiatiefid_queryparam():

    """Buurt Naam Query Parameter Validation for the Natural gas-free Neighborhoods initiatives"""

    buurtinitiatiefidresp = requests.get(datasetconstantinit.dataset_url + "50")
    buurtinitiatiefid_response = buurtinitiatiefidresp.json()

    if buurtinitiatiefid_response["buurtNaam"] is Empty:
        assert buurtinitiatiefid_response["buurtNaam"] == ""
    else:
        assert buurtinitiatiefid_response["buurtNaam"] != ""


@allure.step(
    "Validate the Buurt Type should match with `buurt` in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/50`"
)
def test_buurttypeinitiatiefid_queryparam():

    """Buurt Type Query Parameter Validation for the Natural gas-free Neighborhoods initiatives"""

    buurtinitiatiefidresp = requests.get(datasetconstantinit.dataset_url + "50")
    buurtinitiatiefid_response = buurtinitiatiefidresp.json()

    assert datasetconstantinit.buurtname in buurtinitiatiefid_response["buurtinitiatiefType"]


@allure.step(
    "Validate the coordinate in API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/50`"
)
def test_coordinate_queryparam():

    """Coordinate Query Parameter Validation for the Natural gas-free Neighborhoods initiatives"""

    buurtinitiatiefidresp = requests.get(datasetconstantinit.dataset_url + "50")
    buurtinitiatiefid_response = buurtinitiatiefidresp.json()

    assert buurtinitiatiefid_response["xCoordinaat"] == datasetconstantinit.xCoordinaat
    assert buurtinitiatiefid_response["yCoordinaat"] == datasetconstantinit.yCoordinaat


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/aardgasvrijezones/buurtinitiatief/?page=15` to validate whether the no record found with `failure code 404`"
)
def test_buurtinitiatief_failure():

    """Failure API request for Natural gas-free neighborhoods initiatives"""

    buurtinitiatiefresp = requests.get(datasetconstantinit.dataset_url + "?page=15")
    assert buurtinitiatiefresp.status_code == 404, "Status code not match"
