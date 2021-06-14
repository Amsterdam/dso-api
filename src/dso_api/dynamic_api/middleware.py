import logging

from django.utils.deprecation import MiddlewareMixin
from schematools.contrib.django.auth_backend import RequestProfile

audit_log = logging.getLogger("dso_api.audit")


class DatasetMiddleware(MiddlewareMixin):
    """
    Assign `dataset` to request, for easy access.
    """

    def process_request(self, request):
        request.auth_profile = RequestProfile(request)  # for OAS views

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Make current dataset available across whole application.
        """
        if not hasattr(request, "dataset"):
            try:
                request.dataset = view_func.cls.model._dataset_schema
            except AttributeError:
                pass

        return None


class TemporalTableMiddleware(MiddlewareMixin):
    """
    Assign `versioned`, `table_version` and `temporal_slice` to request.
    """

    def process_request(self, request):
        request.versioned = False
        request.table_version = None
        request.table_temporal_slice = None

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not hasattr(request, "dataset") or not view_func.cls.model.is_temporal():
            return None

        request.versioned = True
        table = view_func.cls.model.table_schema()
        if request.GET.get(table.temporal["identifier"]):
            request.table_version = request.GET.get(table.temporal["identifier"])

        if "dimensions" in table.temporal:
            for key, fields in table.temporal["dimensions"].items():
                if request.GET.get(key):
                    request.table_temporal_slice = dict(
                        key=key, value=request.GET.get(key), fields=fields
                    )

        return None
