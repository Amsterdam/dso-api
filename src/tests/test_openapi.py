import logging

import pytest
from django.urls import reverse

from tests.utils import read_response


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
                "short_name": "afvalwegingen",
                "service_name": "Afvalwegingen",
                "status": "Beschikbaar",
                "description": "unit testing version of afvalwegingen",
                "tags": [],
                "terms_of_use": {
                    "government_only": False,
                    "pay_per_use": False,
                    "license": "CC0 1.0",
                },
                "environments": [
                    {
                        "name": "production",
                        "api_url": f"{base}/v1/afvalwegingen/",
                        "specification_url": f"{base}/v1/afvalwegingen/",
                        "documentation_url": f"{base}/v1/docs/datasets/afvalwegingen.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": f"{base}/v1/wfs/afvalwegingen/"},
                    {"type": "MVT", "url": f"{base}/v1/mvt/afvalwegingen/"},
                ],
                "api_authentication": None,
                "api_type": "unknown",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
            "fietspaaltjes": {
                "id": "fietspaaltjes",
                "short_name": "fietspaaltjes",
                "service_name": "fietspaaltjes",
                "status": "beschikbaar",
                "description": "",
                "tags": [],
                "terms_of_use": {"government_only": False, "pay_per_use": False, "license": None},
                "environments": [
                    {
                        "name": "production",
                        "api_url": f"{base}/v1/fietspaaltjes/",
                        "specification_url": f"{base}/v1/fietspaaltjes/",
                        "documentation_url": f"{base}/v1/docs/datasets/fietspaaltjes.html",
                    }
                ],
                "related_apis": [
                    {"type": "WFS", "url": f"{base}/v1/wfs/fietspaaltjes/"},
                    {"type": "MVT", "url": f"{base}/v1/mvt/fietspaaltjes/"},
                ],
                "api_authentication": None,
                "api_type": "unknown",
                "organization_name": "Gemeente Amsterdam",
                "organization_oin": "00000001002564440000",
                "contact": {
                    "email": "datapunt@amsterdam.nl",
                    "url": "https://github.com/Amsterdam/dso-api/issues",
                },
            },
        }
    }


@pytest.mark.django_db
def test_openapi_swagger(api_client, afval_dataset, filled_router):
    """Prove that the OpenAPI page can be rendered."""
    url = reverse("dynamic_api:openapi-afvalwegingen")
    assert url == "/v1/afvalwegingen/"

    response = api_client.get(url, HTTP_ACCEPT="text/html")
    assert response.status_code == 200
    assert response["content-type"] == "text/html; charset=utf-8"
    content = read_response(response)
    assert "ui.initOAuth(" in content


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

    # Prove that various filters are properly exposed.
    afval_parameters = {
        param["name"]: param
        for param in schema["paths"]["/v1/afvalwegingen/containers/"]["get"]["parameters"]
    }
    all_keys = ", ".join(afval_parameters.keys())
    assert "datumCreatie" in afval_parameters, all_keys
    assert afval_parameters["datumCreatie"] == {
        "name": "datumCreatie",
        "in": "query",
        "description": "yyyy-mm-dd",
        "schema": {"format": "date", "type": "string"},
    }

    # Prove that DSOOrderingFilter exposes parameters
    assert "_format" in afval_parameters, all_keys
    assert afval_parameters["_format"] == {
        "name": "_format",
        "in": "query",
        "schema": {
            "type": "string",
            "enum": ["csv", "geojson", "json"],
        },
    }
    assert "_sort" in afval_parameters, all_keys
    assert afval_parameters["_sort"] == {
        "name": "_sort",
        "in": "query",
        "required": False,
        "description": "Which field to use when ordering the results.",
        "schema": {"type": "string"},
    }

    # Prove that general page parameters are exposed
    assert "_pageSize" in afval_parameters, all_keys
    assert afval_parameters["_pageSize"] == {
        "name": "_pageSize",
        "in": "query",
        "required": False,
        "description": "Number of results to return per page.",
        "schema": {"type": "integer"},
    }

    # Prove that expansion is documented
    assert "_expand" in afval_parameters, all_keys
    assert "_expandScope" in afval_parameters, all_keys
    assert afval_parameters["_expandScope"] == {
        "name": "_expandScope",
        "description": "Comma separated list of named relations to expand.",
        "in": "query",
        "schema": {"type": "string"},
        "examples": {
            "AllValues": {
                "summary": "All Values",
                "value": "cluster",
                "description": "Expand all fields, identical to only using _expand=true.",
            },
            "Cluster": {
                "summary": "cluster",
                "value": "cluster",
            },
        },
    }

    # Prove that the lookups of LOOKUPS_BY_TYPE are parsed
    # ([lt] for dates, [in] for keys)
    assert "datumCreatie[lt]" in afval_parameters, all_keys
    assert "clusterId[in]" in afval_parameters, all_keys
    assert afval_parameters["clusterId[in]"] == {
        "name": "clusterId[in]",
        "in": "query",
        "description": "Multiple values may be separated by commas.",
        "explode": False,
        "schema": {
            "type": "array",
            "items": {"nullable": True, "type": "string"},
        },
        "style": "form",
    }
    assert afval_parameters["clusterId[isnull]"] == {
        "name": "clusterId[isnull]",
        "in": "query",
        "description": "true | false",
        "schema": {"type": "boolean"},
    }

    # Prove that the extra headers are included
    assert "Accept-Crs" in afval_parameters, all_keys
    assert afval_parameters["Accept-Crs"]["in"] == "header"

    log_messages = [m for m in caplog.messages if "DisableMigrations" not in m]
    assert not log_messages, caplog.messages
