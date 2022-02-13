from queue import Empty
import requests
from sqlalchemy import null
from . import datasetconstantbussinv
import pytest


def test_bussinv_success():

    """Success API request for Business Investment zones"""

    bussinvresp=requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_statuscode=bussinvresp.status_code
    assert bussinv_statuscode==200 , "Status code not match"

def test_bussinv_queryparam():

    """Query Parameter Validation for the Business Investment zones"""
    bussinvresp=requests.get(datasetconstantbussinv.dataset_url + "25")
    bussinv_response=bussinvresp.json()

    if (bussinv_response["naam"] is Empty):
        assert bussinv_response["naam"] == ''
    else:
        assert bussinv_response["naam"] != ''

    assert datasetconstantbussinv.naam in bussinv_response["naam"]

    if (bussinv_response["website"] is None):
        assert bussinv_response["website"] is None
    else:
        assert bussinv_response["website"] is not None

    assert bussinv_response["geometry"]["coordinates"][0][0] == datasetconstantbussinv.coordinate

    assert int((datasetconstantbussinv.dataset_url + "25").split("/")[-1]) == bussinv_response["id"]

    assert bussinv_response["heffingsgrondslag"] != 100

    assert "€ " in bussinv_response["heffingstariefDisplay"]

    print(bussinv_response["heffingstariefDisplay"])

    test1="€ " + str(bussinv_response["heffingstarief"])

def test_bussinv_failure():

    """Failure API request for the Business Investment zones"""
    negbussinvresp=requests.get(datasetconstantbussinv.dataset_url + "none")
    negbussinv_statuscode=negbussinvresp.status_code
    assert negbussinv_statuscode==404 , "Status code not match"