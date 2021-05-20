import logging

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_root_view(api_client, afval_dataset, fietspaaltjes_dataset, filled_router, drf_request):
    """Prove that the OpenAPI page can be rendered."""
    url = reverse("dynamic_api:api-root")
    assert url == "/v1/"

    response = api_client.get(url)
    assert response.status_code == 200, response.data

    # Prove that response contains the correct data
    base = drf_request.build_absolute_uri("/").rstrip("/")
    assert response.data == {
        "datasets": {
            "afvalwegingen": {
                "id": "afvalwegingen",
                "name": "afvalwegingen",
                "title": "Afvalwegingen",
                "status": "Beschikbaar",
                "description": "unit testing version of afvalwegingen",
                "api_type": "rest_json",
                "api_url": f"{base}/v1/afvalwegingen/",
                "documentation_url": f"{base}/v1/docs/datasets/afvalwegingen.html",
                "specification_url": f"{base}/v1/swagger/afvalwegingen/",
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "related_apis": [
                    {"type": "wfs", "url": f"{base}/v1/wfs/afvalwegingen/"},
                    {"type": "tiles", "url": f"{base}/v1/mvt/afvalwegingen/"},
                ],
            },
            "fietspaaltjes": {
                "id": "fietspaaltjes",
                "name": "fietspaaltjes",
                "title": "fietspaaltjes",
                "status": "beschikbaar",
                "description": "",
                "api_type": "rest_json",
                "api_url": f"{base}/v1/fietspaaltjes/",
                "documentation_url": f"{base}/v1/docs/datasets/fietspaaltjes.html",
                "specification_url": f"{base}/v1/swagger/fietspaaltjes/",
                "terms_of_use": {"government_only": False, "pay_per_use": False, "license": None},
                "related_apis": [
                    {"type": "wfs", "url": f"{base}/v1/wfs/fietspaaltjes/"},
                    {"type": "tiles", "url": f"{base}/v1/mvt/fietspaaltjes/"},
                ],
            },
        }
    }


@pytest.mark.django_db
def test_openapi_json(api_client, afval_dataset, fietspaaltjes_dataset, filled_router, caplog):
    """Prove that the OpenAPI page can be rendered."""
    caplog.set_level(logging.WARNING)

    # Prove the that OpenAPI view can be found at the endpoint
    url = reverse("dynamic_api:openapi-afvalwegingen")
    assert url == "/v1/afvalwegingen/"

    response = api_client.get(url)
    assert response.status_code == 200, response.data
    assert response["content-type"] == "application/vnd.oai.openapi+json"
    schema = response.data

    # Prove that the main info block is correctly rendered
    assert schema["info"] == {
        "title": "Afvalwegingen",
        "description": "unit testing version of afvalwegingen",
        "version": "0.0.1",
        "license": "CC0 1.0",
        "contact": {"email": "datapunt@amsterdam.nl"},
        "termsOfService": "https://data.amsterdam.nl/",
    }

    # Prove that only afvalwegingen are part of this OpenAPI page:
    paths = sorted(schema["paths"].keys())
    assert paths == [
        "/v1/afvalwegingen/adres_loopafstand/",
        "/v1/afvalwegingen/adres_loopafstand/{id}/",
        "/v1/afvalwegingen/containers/",
        "/v1/afvalwegingen/containers/{id}/",
    ]

    # Prove that the oauth model is exposed
    assert schema["components"]["securitySchemes"]["oauth2"]["type"] == "oauth2"

    # Prove that the serializer field types are reasonably converted
    component_schemas = schema["components"]["schemas"]
    container_properties = component_schemas["Afvalwegingencontainers"]["properties"]
    assert "MultiPolygon" in component_schemas, list(component_schemas)
    assert container_properties["geometry"]["$ref"] == "#/components/schemas/Point"
    assert container_properties["id"]["type"] == "integer"
    assert container_properties["datumLeegmaken"]["format"] == "date-time"

    # Prove that the filter help text is exposed as description
    afval_parameters = {
        param["name"]: param
        for param in schema["paths"]["/v1/afvalwegingen/containers/"]["get"]["parameters"]
    }
    assert "datumCreatie" in afval_parameters, ", ".join(afval_parameters.keys())
    assert afval_parameters["datumCreatie"]["description"] == "yyyy-mm-dd"

    # Prove that DSOOrderingFilter exposes parameters
    assert "_sort" in afval_parameters, ", ".join(afval_parameters.keys())

    # Prove that general page parameters are exposed
    assert "_pageSize" in afval_parameters, ", ".join(afval_parameters.keys())

    # Prove that the lookups of LOOKUPS_BY_TYPE are parsed
    # ([lt] for dates, [in] for keys)
    assert "datumCreatie[lt]" in afval_parameters, ", ".join(afval_parameters.keys())
    assert "clusterId[in]" in afval_parameters, ", ".join(afval_parameters.keys())

    # Prove that the extra headers are included
    assert "Accept-Crs" in afval_parameters, ", ".join(afval_parameters.keys())
    assert afval_parameters["Accept-Crs"]["in"] == "header"

    log_messages = [m for m in caplog.messages if "DisableMigrations" not in m]
    assert not log_messages, caplog.messages
