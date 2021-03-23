"""The paginator classes implement the DSO specific response format for pagination.

This is essentially HAL-JSON style pagination as described in:
https://tools.ietf.org/html/draft-kelly-json-hal-08
"""
from __future__ import annotations

from django.core.paginator import InvalidPage
from rest_framework import pagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.serializers import ListSerializer
from rest_framework.utils.serializer_helpers import ReturnList


class DSOHTTPHeaderPageNumberPagination(pagination.PageNumberPagination):
    """Paginator that only adds the DSO HTTP Header fields:

    * ``X-Pagination-Page``: page number
    * ``X-Pagination-Limit``: page size
    * ``X-Pagination-Count``: number of pages (optional)
    * ``X-Total-Count``: total number of results (optional)

    This can be used for for non-JSON exports (e.g. CSV files).
    """

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
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages

        try:
            self.page = paginator.page(page_number)
        except InvalidPage as exc:
            msg = self.invalid_page_message.format(page_number=page_number, message=str(exc))
            raise NotFound(msg) from exc

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        self.request = request
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
        # Optional but available on this paginator:
        response["X-Pagination-Count"] = paginator.num_pages
        response["X-Total-Count"] = paginator.count
        return response


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


class DSOPageNumberPagination(DSOHTTPHeaderPageNumberPagination):
    """Pagination style as the DSO requires.

    It wraps the response in a few standard objects::

        {
            "_links": {
                "self": {"href": ...},
                "next": {"href": ...},
                "previous": {"href": ...},
            },
            "_embedded": {
                "results_field": [
                    ...,
                    ...,
                ]
            },
            "page": {
                "number": ...,
                "size": ...,
                "totalElements": ...,
                "totalPages": ...,
            }
        }
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
        """Implement DRF hook for completeness, can be used by the browsable API."""
        return data["_embedded"][self.results_field]
