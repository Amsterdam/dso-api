"""Functions needed by various tests"""

import itertools
import json
from io import BytesIO
from types import GeneratorType
from xml.etree import ElementTree as ET

import orjson
from django.apps import apps
from django.http.response import HttpResponseBase
from django.utils.functional import SimpleLazyObject
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from schematools.naming import to_snake_case
from schematools.permissions import UserScopes
from schematools.types import DatasetSchema

from rest_framework_dso.renderers import HALJSONRenderer


def patch_dataset_auth(schema: DatasetSchema, *, auth: list[str]):
    """Monkeypatch an Amsterdam Schema to set "auth" on the complete dataset."""
    schema["auth"] = auth

    # Also patch models of this app
    for vmajor in schema.versions:
        for model in apps.get_app_config(f"{schema.id}_{vmajor}").get_models():
            model.get_dataset_schema()["auth"] = auth


def patch_table_auth(schema: DatasetSchema, table_id, *, auth: list[str]):
    """Monkeypatch an Amsterdam Schema to set "auth" on a table."""
    # This updates the low-level dict data so all high-level objects get it.
    schema.get_table_by_id(table_id)  # checks errors

    raw_table, vmajor = next(
        (t, vmajor)
        for vmajor, version in schema["versions"].items()
        for t in version["tables"]
        if t["id"] == table_id
    )
    raw_table["auth"] = auth

    # Also patch the active model, as that's already loaded and has a copy of the table schema
    model = apps.get_model(f"{schema.id}_{vmajor}", table_id)
    model.table_schema()["auth"] = auth


def patch_field_auth(
    schema: DatasetSchema,
    table_id,
    field_id,
    *subfields: str,
    **update_fields: list[str],
):
    """Monkeypatch an Amsterdam Schema to set "auth" or "filterAuth" on a table."""
    # This updates the low-level dict data so all high-level objects get it.
    table = schema.get_table_by_id(table_id)

    # Patch underlying data that gave rise to it all
    # (needed for fields that read schema data, like DynamicOrderingFilter)
    raw_table, vmajor = next(
        (t, vmajor)
        for vmajor, version in schema["versions"].items()
        for t in version["tables"]
        if t["id"] == table_id
    )
    patch_raw_field_auth(raw_table, field_id, *subfields, **update_fields)

    # table.fields / field.subfields becomes cached property, also update that.
    # (needed for filtering queries that read schema data, like QueryFilterEngine)
    field_schema = table.get_field_by_id(field_id)
    for subfield in subfields:
        field_schema = field_schema.get_field_by_id(subfield)
    field_schema.update(update_fields)

    # Also patch the active model, if its already created (it fetched schema data from database)
    # (needed for serializer fields, these access the model fields to retrieve the schema data)
    if f"{schema.id}_{vmajor}" in apps.app_configs:
        model = apps.get_model(f"{schema.id}_{vmajor}", table_id)
        model._table_schema = table

        model_field = model._meta.get_field(to_snake_case(field_id))
        for subfield in subfields:
            model_field = model_field.related_model._meta.get_field(subfield)

        if model_field.field_schema is not field_schema:
            model_field.field_schema.update(update_fields)


def patch_raw_field_auth(
    raw_table: dict, field_id: str, *subfields: str, **update_fields: list[str]
):
    """Monkeypatch the JSON contents of an Amsterdam Schema to add auth rules."""
    raw_field = next(
        f for f_id, f in raw_table["schema"]["properties"].items() if f_id == field_id
    )

    # Point raw_field to a subfield if this is requested:
    for subfield in subfields:
        # Auto jump over array, object or "array of objects"
        if raw_field["type"] == "array":
            raw_field = raw_field["items"]
        if raw_field["type"] == "object":
            raw_field = raw_field["properties"]

        raw_field = raw_field[subfield]

    # Patch the field
    raw_field.update(update_fields)


def read_response(response: HttpResponseBase) -> str:
    """Read the response content for all response types.
    This works for both HttpResponse, TemplateResponse and StreamingHttpResponse.
    """
    return b"".join(response).decode()


def read_response_json(response: HttpResponseBase, ignore_content_type=False):
    """Shortcut to read response json. This also supports streaming responses.
    Other common approaches won't work in the test code:

    * ``response.json()`` doesn't work with StreamingHttpResponse.
    * ``response.data`` contains consumed generators.
    """
    if not ignore_content_type and "json" not in response["content-type"]:
        raise ValueError(f"Unexpected content type: {response['content-type']} for {response!r}'")

    return orjson.loads(read_response(response))


def read_response_xml(response: HttpResponseBase, ignore_content_type=False) -> ET.Element:
    """Read response XML, and perform the parsing."""
    if not ignore_content_type and "xml" not in response["content-type"]:
        raise ValueError(f"Unexpected content type: {response['content-type']} for {response!r}'")

    return ET.fromstring(read_response(response))


def read_response_partial(response: HttpResponseBase) -> tuple[str, Exception | None]:
    """Read the response content, return partial data when
    streaming was aborted with an exception.
    This works for both HttpResponse, TemplateResponse and StreamingHttpResponse.
    """
    buffer = BytesIO()
    try:
        for chunk in iter(response):
            buffer.write(chunk)
    except Exception as e:  # noqa: B902, BLE001
        return buffer.getvalue().decode(), e
    else:
        return buffer.getvalue().decode(), None


def xml_element_to_dict(element: ET.Element) -> dict:
    """Convert an XML element to a Python dictionary."""
    if not len(element):
        # for recusion into children
        local_name = element.tag.split("}")[1]
        return {local_name: element.text}

    result = {}
    for child in element:
        local_name = child.tag.split("}")[1]
        if len(child) == 0:
            result[local_name] = child.text
        elif len(child) == 1:
            result[local_name] = xml_element_to_dict(child)
        else:
            result[local_name] = [xml_element_to_dict(e) for e in child]

    return result


def normalize_data(data):
    """Turn the data into normal dicts/lists.
    This consumes the generators/itertools.chain.
    It also avoids OrderedDict/GeoDict blurring the output results
    as these become normal dicts too.
    """

    def _default(value):
        if isinstance(value, (GeneratorType, itertools.chain)):
            return list(value)
        raise TypeError

    # Using the Python JSON encoder, since it follows dictionary ordering.
    return orjson.loads(json.dumps(data, default=_default))


def api_request_with_scopes(scopes, data=None) -> Request:
    request = APIRequestFactory().get("/v1/dummy/", data=data)
    request.accept_crs = None  # for DSOSerializer, expects to be used with DSOViewMixin
    request.response_content_crs = None

    request.user_scopes = UserScopes(
        query_params=request.GET,
        request_scopes=scopes,
    )

    # Temporal modifications. Usually done via TemporalTableMiddleware
    request.versioned = False
    return request


def to_drf_request(api_request):
    """Turns an API request into a DRF request."""
    request = Request(api_request)
    request.accepted_renderer = HALJSONRenderer()
    return request


def to_serializer_view(model):
    class DummyView:
        def __init__(self, model):
            self.model = model

    return DummyView(model)


def unlazy(value: SimpleLazyObject):
    """Extract the original object from a SimpleLazyObject()
    so it can be used for 'is' reference comparisons.
    """
    bool(value)
    return value._wrapped
