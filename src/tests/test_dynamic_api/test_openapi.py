import logging

import openapi_spec_validator
import pytest
from django.urls import NoReverseMatch, reverse

from dso_api.dynamic_api import openapi
from tests.utils import read_response


@pytest.mark.django_db
def test_get_patterns(afval_dataset, fietspaaltjes_dataset, filled_router):
    """Prove that the get_dataset_patterns() generates only patterns of a particular view."""
    patterns = openapi.get_dataset_patterns("fietspaaltjes")

    # First prove that both URLs can be resolved in the app
    assert reverse("dynamic_api:afvalwegingen-containers-list")
    assert reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")

    # Then prove that the subset patterns are not providing all URLs
    assert reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list", urlconf=tuple(patterns))
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:afvalwegingen-containers-list", urlconf=tuple(patterns))


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
def test_openapi_swagger_disable(
    api_client, disabled_afval_dataset, fietspaaltjes_dataset, filled_router
):
    """Prove that the OpenAPI page can be rendered."""
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:openapi-afvalwegingen")

    response = api_client.get("/v1/afvalwegingen/", HTTP_ACCEPT="text/html")
    assert response.status_code == 404


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

    openapi_spec_validator.validate_spec(schema)

    # Prove that the main info block is correctly rendered
    assert schema["info"] == {
        "title": "Afvalwegingen",
        "description": "unit testing version of afvalwegingen",
        "version": "0.0.1",
        "license": {"name": "CC0 1.0"},
        "contact": {"email": "datapunt@amsterdam.nl"},
        "termsOfService": "https://data.amsterdam.nl/",
    }

    # Prove that only afvalwegingen are part of this OpenAPI page:
    paths = sorted(schema["paths"].keys())
    assert paths == [
        "/v1/afvalwegingen/adres_loopafstand/",
        "/v1/afvalwegingen/adres_loopafstand/{id}/",
        "/v1/afvalwegingen/clusters/",
        "/v1/afvalwegingen/clusters/{id}/",
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
    assert set(afval_parameters) == {
        "Accept-Crs",
        "Content-Crs",
        "_count",
        "_expand",
        "_expandScope",
        "_fields",
        "_format",
        "_pageSize",
        "_sort",
        "cluster.id",
        "cluster.id[in]",
        "cluster.id[isempty]",
        "cluster.id[isnull]",
        "cluster.id[like]",
        "cluster.id[not]",
        "datumCreatie",
        "datumCreatie[gt]",
        "datumCreatie[gte]",
        "datumCreatie[in]",
        "datumCreatie[isnull]",
        "datumCreatie[lt]",
        "datumCreatie[lte]",
        "datumCreatie[not]",
        "datumLeegmaken",
        "datumLeegmaken[gt]",
        "datumLeegmaken[gte]",
        "datumLeegmaken[in]",
        "datumLeegmaken[isnull]",
        "datumLeegmaken[lt]",
        "datumLeegmaken[lte]",
        "datumLeegmaken[not]",
        "eigenaarNaam",
        "eigenaarNaam[in]",
        "eigenaarNaam[isempty]",
        "eigenaarNaam[isnull]",
        "eigenaarNaam[like]",
        "eigenaarNaam[not]",
        "geometry",
        "geometry[isnull]",
        "geometry[not]",
        "id",
        "id[gt]",
        "id[gte]",
        "id[in]",
        "id[isnull]",
        "id[lt]",
        "id[lte]",
        "id[not]",
        "page",
        "serienummer",
        "serienummer[in]",
        "serienummer[isempty]",
        "serienummer[isnull]",
        "serienummer[like]",
        "serienummer[not]",
    }

    all_keys = ", ".join(afval_parameters.keys())
    assert "datumCreatie" in afval_parameters, all_keys
    assert afval_parameters["datumCreatie"] == {
        "name": "datumCreatie",
        "in": "query",
        "description": "Datum aangemaakt",
        "schema": {"format": "date", "type": "string"},
    }

    # Prove that DSOOrderingFilter exposes parameters
    assert "_format" in afval_parameters, all_keys
    assert afval_parameters["_format"] == {
        "name": "_format",
        "in": "query",
        "description": "Select the export format",
        "schema": {
            "type": "string",
            "enum": ["json", "csv", "geojson"],
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
                "description": "Cluster-ID",
                "summary": "cluster",
                "value": "cluster",
            },
        },
    }

    # Prove that the lookups of LOOKUPS_BY_TYPE are parsed
    # ([lt] for dates, [in] for keys)
    assert "datumCreatie[lt]" in afval_parameters, all_keys
    assert "cluster.id[in]" in afval_parameters, all_keys
    assert afval_parameters["cluster.id[in]"] == {
        "name": "cluster.id[in]",
        "in": "query",
        "description": "Matches any value from a comma-separated list: val1,val2,valN.",
        "explode": False,
        "schema": {
            "type": "array",
            "items": {"type": "string"},
        },
        "style": "form",
    }
    assert afval_parameters["cluster.id[isnull]"] == {
        "name": "cluster.id[isnull]",
        "in": "query",
        "description": "Whether the field has a NULL value or not.",
        "schema": {"type": "boolean"},
    }

    # Prove that the extra headers are included
    assert "Accept-Crs" in afval_parameters, all_keys
    assert afval_parameters["Accept-Crs"]["in"] == "header"

    log_messages = [m for m in caplog.messages if "DisableMigrations" not in m]
    assert not log_messages, caplog.messages


@pytest.mark.django_db
def test_openapi_parkeren_json(api_client, parkeervakken_dataset, filled_router, caplog):
    """Prove that the OpenAPI page can be rendered."""
    caplog.set_level(logging.WARNING)

    # Prove the that OpenAPI view can be found at the endpoint
    url = reverse("dynamic_api:openapi-parkeervakken")
    assert url == "/v1/parkeervakken/"

    response = api_client.get(url)
    assert response.status_code == 200, response.data
    assert response["content-type"] == "application/vnd.oai.openapi+json"
    schema = response.data

    # Prove that various filters are properly exposed.
    parkeervak_parameters = {
        param["name"]: param
        for param in schema["paths"]["/v1/parkeervakken/parkeervakken/"]["get"]["parameters"]
    }
    assert parkeervak_parameters["regimes.dagen"] == {
        "name": "regimes.dagen",
        "description": "Exact; val1,val2",
        "in": "query",
        "schema": {"items": {"type": "string"}, "type": "array"},
        "style": "form",
        "explode": False,
    }
    assert parkeervak_parameters["regimes.dagen[contains]"] == {
        "name": "regimes.dagen[contains]",
        "description": "Matches values from a comma-separated list: val1,val2,valN.",
        "in": "query",
        "schema": {"items": {"type": "string"}, "type": "array"},
        "style": "form",
        "explode": False,
    }
