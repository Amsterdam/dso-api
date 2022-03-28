import os

SCHEMA_URL = os.getenv("SCHEMA_URL", "https://schemas.data.amsterdam.nl/datasets/")
DATAPUNT_API_URL = os.getenv("DATAPUNT_API_URL", "https://acc.api.data.amsterdam.nl")
OIDC_TOKEN_ENDPOINT = os.getenv("OIDC_TOKEN_ENDPOINT")
DATADIENSTEN_TEST_CLIENT_ID = os.getenv("DATADIENSTEN_TEST_CLIENT_ID")
DATADIENSTEN_TEST_CLIENT_SECRET = os.getenv("DATADIENSTEN_TEST_CLIENT_SECRET")
dataset_url = DATAPUNT_API_URL + "/v1/standvastgoed/gebouwen/"
dataset_url_parameter = dataset_url + "2022-01-01.03632000002059CC/?nummeraanduidingVolgnummer=3"
