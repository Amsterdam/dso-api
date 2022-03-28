# Validate String date format
# Using strptime()
from datetime import datetime
from operator import contains
from queue import Empty

import allure
import pytest
import requests
from sqlalchemy import null

from . import datasetconstantgebiedenbuurten


@allure.step(
    "API Call for `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/03630980000012` match to `success code 200`"
)
def test_gebiedenbuurten_success():

    """Success API request for Gebieden Buurten."""

    gebibuurtenresp = requests.get(datasetconstantgebiedenbuurten.dataset_url + "03630980000012")
    assert gebibuurtenresp.status_code == 200, "Status code not match"


@allure.step(
    "Validate begindate format as `date-time` for the API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/03630980000012`"
)
def test_begindate_formatcheck():

    """Check the begin date format as date-time."""

    gebibuurtenresp = requests.get(datasetconstantgebiedenbuurten.dataset_url + "03630980000012")
    gebibuurtendate = gebibuurtenresp.json()

    begindate = gebibuurtendate["beginGeldigheid"]
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
    "Validate documentdatum format as `date` for the API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/03630980000012`"
)
def test_documentdate_formatcheck():

    """Check the documment date format as date."""

    gebibuurtenresp = requests.get(datasetconstantgebiedenbuurten.dataset_url + "03630980000012")
    gebibuurtendate = gebibuurtenresp.json()

    documentdate = gebibuurtendate["documentdatum"]
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
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/?geldigOp=2022-03-25&cbsCode=BU03630301` to check the ununsed `cbsCode`"
)
def test_query_unusedcbscode():

    """Prove that query-ing by `cbsCode` finds Unused Gebieden."""

    payload = {"cbsCode": "BU03630301"}
    gebibuurtenresp = requests.get(
        datasetconstantgebiedenbuurten.payload_parameter_url, params=payload
    )
    content = gebibuurtenresp.json()
    records = content["_embedded"]["buurten"]
    assert len(records) == 0


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/?geldigOp=2022-03-25&cbsCode=BU0363SB01` to check the new `cbsCode`"
)
def test_query_newbuurten():

    """Prove that query-ing by `cbsCode` finds New Gebieden."""

    payload = {"cbsCode": "BU0363SB01"}
    gebibuurtenresp = requests.get(
        datasetconstantgebiedenbuurten.payload_parameter_url, params=payload
    )
    content = gebibuurtenresp.json()
    records = content["_embedded"]["buurten"]
    assert len(records) == 1
    assert records[0]["naam"] == "Weespersluis-Noord"
    assert records[0]["code"] == "SB01"
    assert records[0]["eindGeldigheid"] == None


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/?geldigOp=2022-03-25&cbsCode=BU0363SB01` to check the new `cbsCode` of last 4 charaacter match with the code"
)
def test_query_newcodebuurten():

    """Prove that query-ing by `code` finds New Gebieden."""

    payload = {"cbsCode": "BU0363SB01"}
    gebibuurtenresp = requests.get(
        datasetconstantgebiedenbuurten.payload_parameter_url, params=payload
    )
    content = gebibuurtenresp.json()
    records = content["_embedded"]["buurten"]

    str = records[0]["cbsCode"]
    sliced = str[6:]
    assert sliced == records[0]["code"]


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/?geldigOp=2022-03-25&cbsCode=BU0363SD01` to check the `naam` remain same for the new `cbsCode`"
)
def test_query_existbuurten():

    """Prove that query-ing by `cbsCode` finds existing Gebieden."""

    payload_newversion = {"cbsCode": "BU0363SD01"}
    gebibuurtenresp_newversion = requests.get(
        datasetconstantgebiedenbuurten.payload_parameter_url, params=payload_newversion
    )
    content_newversion = gebibuurtenresp_newversion.json()
    records_newversion = content_newversion["_embedded"]["buurten"]

    payload_oldversion = {"cbsCode": "BU04570002"}
    gebibuurtenresp_oldversion = requests.get(
        datasetconstantgebiedenbuurten.dataset_url, params=payload_oldversion
    )
    content_oldversion = gebibuurtenresp_oldversion.json()
    records_oldversion = content_oldversion["_embedded"]["buurten"]

    # Prove the buurten name should be same as old name for the buurten `cbsCode` change
    assert records_newversion[0]["naam"] == records_oldversion[0]["naam"]


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/0363098000001 to validate whether the no record found with `failure code 404`"
)
def test_buurten_failure():

    """Failure API request for the buurten"""

    gebibuurtenresp = requests.get(datasetconstantgebiedenbuurten.dataset_url + "0363098000001")
    assert gebibuurtenresp.status_code == 404, "Status code not match"


@allure.step(
    "API Call `https://acc.api.data.amsterdam.nl/v1/gebieden/buurten/?geldigOp=foo` match to `Bad request code 400`"
)
def test_buurten_wrong_query_failure():

    """Failure API request for the buurten"""

    payload = {"geldigOp": "foo"}
    gebibuurtenresp = requests.get(datasetconstantgebiedenbuurten.dataset_url, params=payload)
    assert gebibuurtenresp.status_code == 400, "Status code not match"
