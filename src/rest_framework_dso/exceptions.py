"""Additional exception classes"""

from rest_framework import status
from rest_framework.exceptions import APIException


class BadGateway(APIException):
    """Render an HTTP 502 Bad Gateway."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Connection failed (bad gateway)"
    default_code = "bad_gateway"


class ServiceUnavailable(APIException):
    """Render an HTTP 503 Service Unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Connection failed (network trouble)"
    default_code = "service_unavailable"


class GatewayTimeout(APIException):
    """Render an HTTP 504 Gateway Timeout."""

    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = "Connection failed (server timeout)"
    default_code = "gateway_timeout"


class PreconditionFailed(APIException):
    """Render an HTTP 412 Precondition Failed."""

    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_code = "precondition_failed"


class RemoteAPIException(APIException):
    """Indicate that a call to a remote endpoint failed."""

    def __init__(self, title, detail, code, status_code):
        super().__init__(detail, code)
        self.code = code or self.default_code
        self.default_detail = title
        self.status_code = status_code


class HumanReadableException(APIException):
    """Base class for tagging exceptions that can be shown in complete detail to the client.
    This can be shown in the standard exception handler, or during streaming rendering.
    """

    default_detail = "Error during rendering"


class HumanReadableGDALException(HumanReadableException):
    """Tell that rendering failed due to conversion errors"""

    default_detail = "Coordinate conversion failed"
