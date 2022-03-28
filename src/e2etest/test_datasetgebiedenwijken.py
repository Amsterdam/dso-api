import dataclasses

# Validate String date format
# Using strptime()
from datetime import datetime
from operator import contains
from queue import Empty

import allure
import pytest
import requests
from more_itertools import iterate
from sqlalchemy import null

from . import datasetconstantgebiedenwijken

allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/03630970000000.2` match to `success code 200`"
)


def test_gebiedenwijken_success():

    """Success API request for Gebieden Wijken."""

    gebiwijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url + "03630970000000.2")
    assert gebiwijkenresp.status_code == 200, "Status code not match"


allure.step(
    "Validate begindate format as `date-time` for the API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/03630970000000.2`"
)


def test_begindate_formatcheck():

    """Check the begin date format as date-time."""

    gebiwijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url + "03630970000000.2")
    gebiwijkendate = gebiwijkenresp.json()

    begindate = gebiwijkendate["beginGeldigheid"]
    # initializing format
    format = "%Y-%m-%dT%H:%M:%S"

    # checking if format matches the date
    res = True

    # using try-except to check for truth value
    try:
        res = bool(datetime.strptime(begindate, format))
    except ValueError:
        res = False

    assert str(res) == "True"


@allure.step(
    "Validate documentdatum format as `date` for the API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/03630970000000.2`"
)
def test_documentdate_formatcheck():

    """Check the documment date format as date."""

    gebiwijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url + "03630970000000.2")
    gebiwijkendate = gebiwijkenresp.json()

    documentdate = gebiwijkendate["documentdatum"]
    # initializing format
    format = "%Y-%m-%dT%H:%M:%S"

    # checking if format matches the date
    res = True

    # using try-except to check for truth value
    try:
        res = bool(datetime.strptime(documentdate, format))
    except ValueError:
        res = False

    assert str(res) == "False"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/?geldigOp=2022-03-25&cbsCode=WK0363FC` to check the new `cbsCode`"
)
def test_query_newwijken():

    """Prove that query-ing by `cbsCode` finds New Wijken."""

    payload = {"cbsCode": "WK0363FC"}
    gebiwijkenresp = requests.get(
        datasetconstantgebiedenwijken.payload_parameter_url, params=payload
    )
    content = gebiwijkenresp.json()
    records = content["_embedded"]["wijken"]
    assert len(records) == 1
    assert records[0]["naam"] == "Slotermeer-West"
    assert records[0]["code"] == "FC"
    assert records[0]["eindGeldigheid"] == None


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/?geldigOp=2022-03-25&cbsCode=WK0363SB` to check the `naam` remain same for the new `cbsCode`"
)
def test_query_existwijken():

    """Prove that query-ing by `cbsCode` finds existing Wijken."""

    payload_newversion = {"cbsCode": "WK0363SB"}
    gebiwijkenresp_newversion = requests.get(
        datasetconstantgebiedenwijken.payload_parameter_url, params=payload_newversion
    )
    content_newversion = gebiwijkenresp_newversion.json()
    records_newversion = content_newversion["_embedded"]["wijken"]

    payload_oldversion = {"cbsCode": "WK045709"}
    gebiwijkenresp_oldversion = requests.get(
        datasetconstantgebiedenwijken.dataset_url, params=payload_oldversion
    )
    content_oldversion = gebiwijkenresp_oldversion.json()
    records_oldversion = content_oldversion["_embedded"]["wijken"]

    # Prove the Wijken name should be same as old name for the wijken `code` change
    assert records_newversion[0]["naam"] == records_oldversion[0]["naam"]


@allure.step(
    "API Call https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/?geldigOp=2022-03-25&cbsCode=WK0363SB to check the new `cbsCode` of last 4 charaacter match with the code"
)
def test_query_newcodewijken():

    """Prove that query-ing by `code` finds New Wijken."""

    payload = {"cbsCode": "WK0363SB"}
    gebiwijkenresp = requests.get(
        datasetconstantgebiedenwijken.payload_parameter_url, params=payload
    )
    content = gebiwijkenresp.json()
    records = content["_embedded"]["wijken"]

    str = records[0]["cbsCode"]
    sliced = str[6:]

    assert sliced == records[0]["code"]


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/` to check whether existing length of code to be 3"
)
def test_query_lengthcodewijken():

    """Prove that query-ing finds existing length of the `code` Wijken."""

    codewijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url)
    content = codewijkenresp.json()
    records = content["_embedded"]["wijken"]

    i = 0
    while i < 10:
        assert len(records[i]["code"]) == 3
        i += 1


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/?geldigOp=2022-03-25` to check whether new length of code to be 2"
)
def test_query_lengthcodeexisitingwijken():

    """Prove that query-ing finds modified length of the `code` Wijken."""

    codewijkenresp = requests.get(datasetconstantgebiedenwijken.payload_parameter_url)
    content = codewijkenresp.json()
    records = content["_embedded"]["wijken"]

    i = 0
    while i < 10:
        assert len(records[i]["code"]) == 2
        i += 1


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/0363097000000C to validate whether the no record found with `failure code 404`"
)
def test_Wijken_failure():

    """Failure API request for the Wijken"""

    gebiwijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url + "0363097000000C")
    assert gebiwijkenresp.status_code == 404, "Status code not match"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/wijken/?geldigOp=foo` match to `Bad request code 400`"
)
def test_Wijken_wrong_query_failure():

    """Failure API request for the Wijken"""

    payload = {"geldigOp": "foo"}
    gebiwijkenresp = requests.get(datasetconstantgebiedenwijken.dataset_url, params=payload)
    assert gebiwijkenresp.status_code == 400, "Status code not match"
