import logging

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_openapi_json(api_client, filled_router, caplog):
    """Prove that the OpenAPI page can be rendered."""
    caplog.set_level(logging.WARNING)

    url = reverse("openapi.json")
    response = api_client.get(url)
    assert response.status_code == 200, response.data
    schema = response.data

    # Prove that the oauth model is exposed
    assert schema["components"]["securitySchemes"]["oauth2"]["type"] == "oauth2"

    # Prove that the serializer field types are reasonably converted
    component_schemas = schema["components"]["schemas"]
    container_properties = component_schemas["AfvalwegingenContainers"]["properties"]
    assert "MultiPolygon" in component_schemas, list(component_schemas)
    assert container_properties["geometry"]["$ref"] == "#/components/schemas/Point"
    assert container_properties["id"]["type"] == "integer"
    assert container_properties["datumLeegmaken"]["format"] == "date-time"

    # Prove that the filter help text is exposed as description
    afval_parameters = {
        param["name"]: param
        for param in schema["paths"]["/v1/afvalwegingen/containers/"]["get"][
            "parameters"
        ]
    }
    assert "datumCreatie" in afval_parameters, ", ".join(afval_parameters.keys())
    assert afval_parameters["datumCreatie"]["description"] == "yyyy-mm-dd"

    # Prove that DSOOrderingFilter exposes parameters
    assert "_sort" in afval_parameters, ", ".join(afval_parameters.keys())

    # Prove that the lookups of LOOKUPS_BY_TYPE are parsed
    # ([lt] for dates, [in] for keys)
    assert "datumCreatie[lt]" in afval_parameters, ", ".join(afval_parameters.keys())
    assert "clusterId[in]" in afval_parameters, ", ".join(afval_parameters.keys())

    assert not caplog.messages


@pytest.mark.django_db
def test_openapi_yaml(api_client, filled_router):
    """Prove that the OpenAPI page can be rendered."""
    url = reverse("openapi.yaml")
    response = api_client.get(url)
    assert response.status_code == 200, response.data
