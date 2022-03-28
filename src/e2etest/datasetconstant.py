import os

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://acc.api.data.amsterdam.nl")
dataset_url = DATAPUNT_API_URL + "/v1/aardgasvrijezones/buurt/"

coordinate = [121603.01819999982, 492216.9764, 0.0]
buurtname = "buurt"
