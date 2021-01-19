from __future__ import annotations

from rest_framework import pagination
from rest_framework.response import Response
from rest_framework.serializers import ListSerializer
from rest_framework.utils.serializer_helpers import ReturnList


class DSOHTTPHeaderPageNumberPagination(pagination.PageNumberPagination):
    """Pagination style for non-JSON exports.
    This doesn't add next/previous content to the CSV file.
    Instead, only HTTP headers are added.
    """

    # Using underscore as "escape" for DSO compliance.
    page_query_param = "page"  # standard still maintains this format..
    page_size_query_param = "_pageSize"

    #: The field name for the results envelope
    results_field = None

    def __init__(self, results_field=None):
        if results_field:
            self.results_field = results_field

    def get_page_size(self, request):
        if self.page_size_query_param not in request.query_params:
            # Allow our classic rest "page_size" setting that we leaked into
            # the public API to be used as fallback. This only affects the
            # current request (attribute is set on self, not the class).
            if "page_size" in request.query_params:
                self.page_size_query_param = "page_size"

        return super().get_page_size(request)

    def get_paginated_response(self, data):
        response = Response(data)  # no content added!
        response["X-Pagination-Page"] = self.page.number

        paginator = self.page.paginator
        response["X-Pagination-Limit"] = paginator.per_page
        # Optional but available on this paginator:
        response["X-Pagination-Count"] = paginator.num_pages
        response["X-Total-Count"] = paginator.count
        return response


class DelegatedPageNumberPagination(DSOHTTPHeaderPageNumberPagination):
    """Delegate the pagination rendering to the output renderer."""

    def get_paginated_response(self, data):
        # Inform the renderer about the known pagination details.
        self.request.accepted_renderer.setup_pagination(self)
        return super().get_paginated_response(data)


class DSOPageNumberPagination(DSOHTTPHeaderPageNumberPagination):
    """
    Implement pagination as the DSO requires.

    This is essentially HAL-JSON style pagination as described in:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    #: The field name for the results envelope
    results_field = None

    def __init__(self, results_field=None):
        if results_field:
            self.results_field = results_field

    def get_paginated_response(self, data):
        # Add the _links, and add the HTTP headers.
        data = self._get_paginated_data(data)
        return super().get_paginated_response(data)

    def _get_paginated_data(self, data: ReturnList) -> dict:
        # Avoid adding ?_expand=.. and other parameters in the 'self' url.
        self_link = self.request.build_absolute_uri(self.request.path)
        if self_link.endswith(".api"):
            self_link = self_link[:-4]

        next_link = self.get_next_link()
        prev_link = self.get_previous_link()

        # As Python 3.6 preserves dict ordering, no longer using OrderedDict.
        # While DSO 2.0 shows "prev", the HAL-JSON standard uses "previous".
        _links = {
            "self": {"href": self_link},
            "next": {"href": next_link},
            "previous": {"href": prev_link},
        }

        paginator = self.page.paginator
        page = {
            "number": self.page.number,
            "size": paginator.per_page,
            "totalElements": paginator.count,
            "totalPages": paginator.num_pages,
        }

        if isinstance(data, dict):
            # Used DSOListSerializer, already received multiple lists
            return {
                "_links": _links,
                "_embedded": data,
                "page": page,
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
                "_links": _links,
                "_embedded": {results_field: data},
                "page": page,
            }

    def get_results(self, data):
        return data["_embedded"][self.results_field]
