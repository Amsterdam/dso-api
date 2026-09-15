import requests

from integration_tests import settings


def get_entra_token() -> str:
    # In local development use a token set in the environment
    if settings.TOKEN:
        return settings.TOKEN

    tenant_id = settings.TENANT_ID
    client_id = settings.CLIENT_ID
    client_secret = settings.CLIENT_SECRET
    scope = settings.SCOPE

    body = (
        f"grant_type=client_credentials&client_id={client_id}&"
        f"client_secret={client_secret}&scope={scope}"
    )

    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        body,
        headers={"ContentType": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    return response.json()["access_token"]


def get_keycloak_token() -> str:
    # In local development use a token set in the environment
    if settings.KEYCLOAK_TOKEN:
        return settings.KEYCLOAK_TOKEN

    tenant_id = settings.TENANT_ID
    client_id = settings.CLIENT_ID
    client_secret = settings.CLIENT_SECRET
    scope = settings.SCOPE

    body = (
        f"grant_type=client_credentials&client_id={client_id}&"
        f"client_secret={client_secret}&scope={scope}"
    )

    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        body,
        headers={"ContentType": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    return response.json()["access_token"]
