"""Functions needed by various tests"""
import itertools
import json
from types import GeneratorType

import orjson
from django.http.response import HttpResponseBase


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
