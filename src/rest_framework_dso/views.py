from typing import Optional

from gisserver.types import CRS
from rest_framework.exceptions import NotAcceptable
from rest_framework.views import exception_handler as drf_exception_handler

from rest_framework_dso import crs, parsers
from rest_framework_dso.exceptions import PreconditionFailed


def exception_handler(exc, context):
    """Return the exceptions as 'application/problem+json'."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    # DRF parsed the exception as API
    detail = response.data["detail"]
    response.data = {
        "type": f"urn:apiexception:{detail.code}",
        "detail": str(detail),
        "status": response.status_code,
    }

    # Returning a response with explicit content_type breaks the browsable API,
    # as that only returns text/html as it's default type.
    response.content_type = "application/problem+json"
    return response


class DSOViewMixin:
    """Basic logic for all DSO-based views"""

    #: The list of allowed coordinate reference systems for the request header
    accept_crs = {crs.RD_NEW, crs.WEB_MERCATOR, crs.ETRS89, crs.WGS84}

    #: If there is a geo field, DSO requires that Accept-Crs is set.
    accept_crs_required = False

    #: Enforce parsing Content-Crs for POST requests:
    parser_classes = [parsers.DSOJsonParser]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        request.accept_crs = self._parse_accept_crs(request.META.get("HTTP_ACCEPT_CRS"))
        request.response_content_crs = None

    def _parse_accept_crs(self, http_value) -> Optional[CRS]:
        """Parse the HTTP Accept-Crs header.

        Clients provide this header to indicate which CRS
        they would like to have in the response.
        """
        if not http_value:
            if self.accept_crs_required:
                # This makes Accept-Crs mandatory
                raise PreconditionFailed("The HTTP Accept-Crs header is required")
            else:
                return None

        try:
            accept_crs = CRS.from_string(http_value)
        except ValueError as e:
            raise NotAcceptable(f"Chosen CRS is invalid: {e}") from e

        if accept_crs not in self.accept_crs:
            raise NotAcceptable(f"Chosen CRS is not supported: {accept_crs}")
        return accept_crs

    def finalize_response(self, request, response, *args, **kwargs):
        """Set the Content-Crs header if there was a geometry field."""
        # The logic from initial() won't be executed if there is an early parser exception.
        accept_crs = getattr(request, "accept_crs", None)
        content_crs = getattr(request, "response_content_crs", None) or accept_crs
        if content_crs is not None:
            response["Content-Crs"] = str(content_crs)

        return super().finalize_response(request, response, *args, **kwargs)
