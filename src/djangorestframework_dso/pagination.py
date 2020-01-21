from rest_framework import pagination, response


class DSOPageNumberPagination(pagination.PageNumberPagination):
    """
    Implement pagination as the DSO requires.

    This is essentially HAL-JSON style pagination as described in:
    https://tools.ietf.org/html/draft-kelly-json-hal-08
    """

    #: The field name for the results envelope
    results_field = 'results'

    def __init__(self, results_field=None):
        if results_field:
            self.results_field = results_field

    def get_paginated_response(self, data):
        data = self._get_paginated_data(data)
        return response.Response(data)

    def _get_paginated_data(self, data) -> dict:
        self_link = self.request.build_absolute_uri()
        if self_link.endswith(".api"):
            self_link = self_link[:-4]

        next_link = self.get_next_link()
        prev_link = self.get_previous_link()

        # As Python 3.6 preserves dict ordering, no longer using OrderedDict.
        _links = {
            'self': {'href': self_link},
            'next': {'href': next_link},
            'previous': {'href': prev_link},
        }

        if isinstance(data, dict):
            # Used DSOListSerializer, already received multiple lists
            return {
                '_links': _links,
                'count': self.page.paginator.count,
                'page_size': self.page_size,
                '_embedded': data,
            }
        else:
            # Regular list serializer, wrap in HAL fields.
            return {
                '_links': _links,
                'count': self.page.paginator.count,
                'page_size': self.page_size,
                '_embedded': {
                    self.results_field: data,
                }
            }

    def get_results(self, data):
        return data['_embedded'][self.results_field]
