from queue import Empty
import requests
from sqlalchemy import null
from . import datasetconstant
from . import datasetconstantinit
import pytest

def test_buurtid_success():

    """Success API request for Natural gas-free neighborhoods"""

    buurtidresp=requests.get(datasetconstant.dataset_url + "475")
    buurtid_statuscode=buurtidresp.status_code
    assert buurtid_statuscode==200 , "Status code not match"

def test_buurtid_queryparam():

    """Query Parameter Validation for the Natural gas-free Neighborhoods"""
   
    buurtidresp=requests.get(datasetconstant.dataset_url + "475")
    buurtid_response=buurtidresp.json()

    if (buurtid_response["buurtNaam"] is Empty):
        assert buurtid_response["buurtNaam"] == ''
    else:
        assert buurtid_response["buurtNaam"] != ''

    assert datasetconstant.buurtname in buurtid_response["buurtNaam"]

    if (buurtid_response["buurtCode"] is null):
        assert buurtid_response["buurtCode"] is None
    else:
        assert buurtid_response["buurtCode"] is not None

    assert buurtid_response["geometry"]["coordinates"][0][0][0] == datasetconstant.coordinate

    if (buurtid_response["aandeelKookgas"] is None):
        assert buurtid_response["aandeelKookgas"] is None
    else:
        assert buurtid_response["aandeelKookgas"] is not None

def test_buurtinitiatiefid_success():

    """Success API request for Natural gas-free neighborhoods initiatives"""

    buurtinitiatiefidresp=requests.get(datasetconstantinit.dataset_url + "50")
    buurtinitiatiefid_statuscode=buurtinitiatiefidresp.status_code
    assert buurtinitiatiefid_statuscode==200 , "Status code not match"

def test_buurtinitiatiefid_queryparam():

    """Query Parameter Validation for the Natural gas-free Neighborhoods"""
    buurtinitiatiefidresp=requests.get(datasetconstantinit.dataset_url + "50")  
    buurtinitiatiefid_response=buurtinitiatiefidresp.json()

    assert int((datasetconstantinit.dataset_url + "50").split("/")[-1]) == buurtinitiatiefid_response["id"]

    if (buurtinitiatiefid_response["buurtNaam"] is Empty):
        assert buurtinitiatiefid_response["buurtNaam"] == ''
    else:
        assert buurtinitiatiefid_response["buurtNaam"] != ''

    assert datasetconstantinit.buurtname in buurtinitiatiefid_response["buurtinitiatiefType"]
    assert buurtinitiatiefid_response["xCoordinaat"] == datasetconstantinit.xCoordinaat
    assert buurtinitiatiefid_response["yCoordinaat"] == datasetconstantinit.yCoordinaat

def test_buurtinitiatief_failure():

    """Failure API request for Natural gas-free neighborhoods initiatives"""

    buurtinitiatiefresp=requests.get(datasetconstantinit.dataset_url + "?page=15")
    buurtinitiatief_statuscode=buurtinitiatiefresp.status_code
    assert buurtinitiatief_statuscode==404 , "Status code not match"