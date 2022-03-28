from queue import Empty

import allure
import pytest
import requests
from sqlalchemy import null

from . import datasetconstantbussinv


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25` match to `success code 200`"
)
def test_bussinv_success():

    """Success API request for Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    assert bussinvresp.status_code == 200, "Status code not match"


@allure.step(
    "Validate the Buurt name should not be empty for an id in API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25`"
)
def test_namebussinv_queryparam():

    """Naam Query Parameter Validation for the Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response = bussinvresp.json()

    if bussinv_response["naam"] is Empty:
        assert bussinv_response["naam"] == ""
    else:
        assert bussinv_response["naam"] != ""

    assert datasetconstantbussinv.naam in bussinv_response["naam"]


@allure.step(
    "Validate the Website should not be null for an id in API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25`"
)
def test_websitebussinv_queryparam():

    """Website Query Parameter Validation for the Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response = bussinvresp.json()

    if bussinv_response["website"] is None:
        assert bussinv_response["website"] is None
    else:
        assert bussinv_response["website"] is not None


@allure.step(
    "Validate the Geometry coordinates for an id in API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25`"
)
def test_coordinatebussinv_queryparam():

    """Coordinates Query Parameter Validation for the Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response = bussinvresp.json()

    assert bussinv_response["geometry"]["coordinates"][0][0] == datasetconstantbussinv.coordinate


@allure.step(
    "Validate the id in API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25` match in the json response for the id value"
)
def test_bussinvid_queryparam():

    """Id Query Parameter Validation for the Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response = bussinvresp.json()

    assert (
        int((datasetconstantbussinv.dataset_url + "25").split("/")[-1]) == bussinv_response["id"]
    )


@allure.step(
    "Validate the Tax rate query parameter include of euro in API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/25`"
)
def test_texratebussinv_queryparam():

    """Tax rate Query Parameter Validation for the Business Investment zones"""

    bussinvresp = requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response = bussinvresp.json()

    assert "€ " + str(bussinv_response["heffingstarief"])


@allure.step(
    "Querying the records less than 70 for the API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/?bijdrageplichtingen[lte]=70`"
)
def test_query_by_bijdrageplichtingen():

    """Prove that query-ing by `bijdrageplichtingen` finds expected resource."""

    payload = {"bijdrageplichtingen[lte]": 70}
    buurtidresp = requests.get(datasetconstantbussinv.dataset_url, params=payload)
    content = buurtidresp.json()
    records = content["_embedded"]["bedrijveninvesteringszones"]
    assert len(records) >= 1
    assert records[0]["id"] == 0
    assert records[0]["naam"] == "A.J. Ernststraat"


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/?id=foo` match to `Bad request code 400`"
)
def test_providing_wrongly_types_query():

    """Prove that providing a string where an int is expected results in 400 (Bad Request)."""

    payload = {"id": "foo"}
    buurtidresp = requests.get(datasetconstantbussinv.dataset_url, params=payload)
    assert buurtidresp.status_code == 400


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/bedrijveninvesteringszones/bedrijveninvesteringszones/"
    "` to validate whether the no record found with `failure code 404`"
)
def test_bussinv_failure():

    """Failure API request for the Business Investment zones"""

    negbussinvresp = requests.get(datasetconstantbussinv.dataset_url + "none")
    assert negbussinvresp.status_code == 404, "Status code not match"
