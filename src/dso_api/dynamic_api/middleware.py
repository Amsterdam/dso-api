import logging

from django.utils.deprecation import MiddlewareMixin
from schematools.contrib.django.models import Profile
from schematools.permissions import UserScopes

audit_log = logging.getLogger("dso_api.audit")


class DatasetMiddleware(MiddlewareMixin):
    """
    Assign `dataset` to request, for easy access.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        # Load the profiles once on startup of the application (just like datasets are read once).
        self.all_profiles = [p.schema for p in Profile.objects.all()]

    def process_request(self, request):
        # This also installs the `user_scopes` for the OAS views.
        request.user_scopes = UserScopes(request.GET, request.is_authorized_for, self.all_profiles)

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
        try:
            if not view_func.cls.model.is_temporal():
                return None
        except AttributeError:
            return None

        request.versioned = True
        table = view_func.cls.model.table_schema()
        if version := request.GET.get(table.temporal.identifier):
            request.table_version = version

        for key, fields in table.temporal.dimensions.items():
            if request.GET.get(key):
                request.table_temporal_slice = dict(
                    key=key, value=request.GET.get(key), fields=fields
                )

        return None
