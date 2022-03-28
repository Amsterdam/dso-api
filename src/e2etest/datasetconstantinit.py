import os

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://acc.api.data.amsterdam.nl")
dataset_url = DATAPUNT_API_URL + "/v1/aardgasvrijezones/buurtinitiatief/"

buurtname = "buurt"
xCoordinaat = 119834.554952
yCoordinaat = 486271.320283
