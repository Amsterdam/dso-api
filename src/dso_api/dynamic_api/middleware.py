class BaseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)


class DatasetMiddleware(BaseMiddleware):
    """
    Assign `dataset` to request, for easy access.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Make current dataset available across whole application.
        """
        if not hasattr(request, "dataset"):
            try:
                request.dataset = view_func.cls.model._dataset_schema
            except AttributeError:
                request.dataset = None

        if request.dataset is not None and request.dataset.id == "bagh":
            request.dataset.versioning = dict(
                request_parameter="versie",
                version_field_name="volgnummer",
                pk_field_name="identificatie",
                temporal=dict(geldigOp=["begin_geldigheid", "eind_geldigheid"]),
            )

        return None


class TemporalDatasetMiddleware(BaseMiddleware):
    """
    Assign `dateset_verison` and `dataset_temporal_slice` to request.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.dataset_version = None
        request.dataset_temporal_slice = None

        if not hasattr(request, "dataset") or not hasattr(
            request.dataset, "versioning"
        ):
            return None

        if request.GET.get(request.dataset.versioning["request_parameter"]):
            request.dataset_version = request.GET.get(
                request.dataset.versioning["request_parameter"]
            )

        if "temporal" in request.dataset.versioning:
            for key, fields in request.dataset.versioning["temporal"].items():
                if request.GET.get(key):
                    request.dataset_temporal_slice = dict(
                        key=key, value=request.GET.get(key), fields=fields
                    )

        return None
