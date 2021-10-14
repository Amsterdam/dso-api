"""The paginator classes implement the DSO specific response format for pagination.

This is essentially HAL-JSON style pagination as described in:
https://tools.ietf.org/html/draft-kelly-json-hal-08
"""
from __future__ import annotations

from typing import Union

from django.core.paginator import InvalidPage
from rest_framework import pagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.serializers import ListSerializer
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList

from rest_framework_dso.serializer_helpers import ReturnGenerator

from .paginator import DSOPaginator


class DSOHTTPHeaderPageNumberPagination(pagination.PageNumberPagination):
    """Paginator that only adds the DSO HTTP Header fields:

    * ``X-Pagination-Page``: page number
    * ``X-Pagination-Limit``: page size
    * ``X-Pagination-Count``: number of pages (optional)
    * ``X-Total-Count``: total number of results (optional)

    This can be used for for non-JSON exports (e.g. CSV files).
    """

    django_paginator_class = DSOPaginator

    # Using underscore as "escape" for DSO compliance.

    #: The page number query parameter.
    page_query_param = "page"  # standard still maintains this format..

    #: The page size query parameter.
    page_size_query_param = "_pageSize"

    def paginate_queryset(self, queryset, request, view=None):
        """Optimized base class logic, to return a queryset instead of list."""
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = request.query_params.get(self.page_query_param, 1)

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(page_number=page_number, message=str(exc))
            raise NotFound(msg) from exc

        self.request = request
        self.include_count = self.request.query_params.get("_count") == "true"
        return self.page.object_list  # original: list(self.page)

    def get_page_size(self, request):
        """Allow the ``page_size`` parameter was fallback."""
        if self.page_size_query_param not in request.query_params:
            # Allow our classic rest "page_size" setting that we leaked into
            # the public API to be used as fallback. This only affects the
            # current request (attribute is set on self, not the class).
            if "page_size" in request.query_params:
                self.page_size_query_param = "page_size"

        return super().get_page_size(request)

    def get_paginated_response(self, data) -> Response:
        """Adds the DSO HTTP headers only.
        It wraps the data in the :class:`~rest_framework.response.Response` object.
        """
        response = Response(data)  # no content added!
        response["X-Pagination-Page"] = self.page.number

        paginator = self.page.paginator
        response["X-Pagination-Limit"] = paginator.per_page

        if self.include_count:
            response["X-Total-Count"] = self.page.paginator.count
            response["X-Pagination-Count"] = self.page.paginator.num_pages

        return response

    def get_schema_operation_parameters(self, view):
        parameters = super().get_schema_operation_parameters(view)
        return parameters + [
            {
                "name": "_count",
                "required": False,
                "in": "query",
                "description": """
                    Include a count of the total result set and the number of pages.
                    Only works for responses that return a page.""",
                "schema": {
                    "type": "boolean",
                },
            },
        ]


class DelegatedPageNumberPagination(DSOHTTPHeaderPageNumberPagination):
    """Delegate the pagination rendering to the output renderer.

    In the design of Django-Rest-Framework, the output renderer and pagination
    are separate object types. While such approach sort-of works for JSON-style
    responses, it's problematic for other file formats such as CSV/GeoJSON.

    Instead of letting the paginator render the pagination for various formats,
    this renderer class delegates that task to the current output renderer.
    For this, the output renderer class must implement a ``setup_pagination()`` function.
    """

    def get_paginated_response(self, data):
        # Inform the renderer about the known pagination details.
        self.request.accepted_renderer.setup_pagination(self)
        return super().get_paginated_response(data)


class DSOPageNumberPagination(DelegatedPageNumberPagination):
    """Pagination style as the DSO requires.

    It wraps the response in a few standard objects::

        {
            "_embedded": {
                "results_field": [
                    ...,
                    ...,
                ]
            },
            "_links": {
                "self": {"href": ...},
                "next": {"href": ...},
                "previous": {"href": ...},
            },
            "page": {
                "number": ...,
                "size": ...,
                "totalElements": ...,
                "totalPages": ...,
            }
        }

        The '_links' and 'page' attribute can be retrieved with the get_footer method,
        after the result_field has been streamed so the number of items in the result_set is known.
    """

    #: The field name for the results envelope
    results_field = None

    def __init__(self, results_field=None):
        """Allow to override the ``results_field`` on construction"""
        if results_field:
            self.results_field = results_field

    def get_paginated_response(self, data):
        """Wrap the data in all pagination parts."""
        # Add the _links, and add the HTTP headers.
        data = self._get_paginated_data(data)
        return super().get_paginated_response(data)

    def _get_paginated_data(self, data: Union[ReturnList, ReturnDict, ReturnGenerator]) -> dict:
        if isinstance(data, dict):
            # Used DSOListSerializer, already received multiple lists
            return {
                "_embedded": data,
            }
        else:
            # Regular list serializer, wrap in HAL fields.
            if self.results_field:
                results_field = self.results_field
            else:
                serializer = data.serializer
                if isinstance(data.serializer, ListSerializer):
                    serializer = serializer.child
                results_field = serializer.Meta.model._meta.model_name
            return {
                "_embedded": {results_field: data},
            }

    def get_footer(self) -> dict:
        """Generate the links and page fields"""
        return {"_links": self.get_links(), "page": self.get_page()}

    def get_links(self) -> dict:
        """Generate the links field"""
        self_link = self.request.build_absolute_uri()
        if self_link.endswith(".api"):
            self_link = self_link[:-4]

        # As Python 3.6 preserves dict ordering, no longer using OrderedDict.
        # While DSO 2.0 shows "prev", the HAL-JSON standard uses "previous".
        _links = {
            "self": {"href": self_link},
        }

        if (next_link := self.get_next_link()) is not None:
            _links["next"] = {"href": next_link}
        if (prev_link := self.get_previous_link()) is not None:
            _links["previous"] = {"href": prev_link}
        return _links

    def get_page(self) -> dict:
        """Generate the page field"""
        page = {
            "number": self.page.number,
            "size": self.page.paginator.per_page,
        }
        if self.include_count:
            page["totalElements"] = self.page.paginator.count
            page["totalPages"] = self.page.paginator.num_pages

        return page

    def get_results(self, data):
        """Implement DRF hook for completeness, can be used by the browsable API."""
        return data["_embedded"][self.results_field]

    def get_paginated_response_schema(self, schema: dict) -> dict:
        """Tell what the OpenAPI schema looks like.
        This is directly used by the OpenAPI results for paginated views.
        """
        demo_url = "https://api.data.amsterdam.nl/v1/.../resource/"
        return {
            "type": "object",
            "properties": {
                "page": {
                    "type": "object",
                    "properties": {
                        "number": {
                            "type": "integer",
                            "example": 3,
                        },
                        "size": {
                            "type": "integer",
                            "example": self.page_size,
                        },
                        "totalElements": {
                            "type": "integer",
                            "example": 5,
                        },
                        "totalPages": {
                            "type": "integer",
                            "example": 3,
                        },
                    },
                },
                "_links": {
                    "type": "object",
                    "properties": {
                        "self": {
                            "type": "object",
                            "properties": {
                                "href": {
                                    "type": "string",
                                    "format": "uri",
                                    "example": f"{demo_url}?{self.page_query_param}=3",
                                },
                            },
                        },
                        "next": {
                            "type": "object",
                            "properties": {
                                "href": {
                                    "type": "string",
                                    "nullable": True,
                                    "format": "uri",
                                    "example": f"{demo_url}?{self.page_query_param}=4",
                                },
                            },
                        },
                        "previous": {
                            "type": "object",
                            "properties": {
                                "href": {
                                    "type": "string",
                                    "nullable": True,
                                    "format": "uri",
                                    "example": f"{demo_url}?{self.page_query_param}=2",
                                },
                            },
                        },
                    },
                },
                "_embedded": {
                    "type": "object",
                    "properties": {
                        self.results_field or "OBJECT_NAME": schema,
                    },
                },
            },
        }
