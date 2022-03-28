import os

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://acc.api.data.amsterdam.nl")
dataset_url = DATAPUNT_API_URL + "/v1/gebieden/buurten/"
payload_parameter_url = dataset_url + "?geldigOp=2022-03-25"
