from rest_framework import status
from rest_framework.exceptions import APIException


class BadGateway(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Connection failed (bad gateway)"
    default_code = "bad_gateway"


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Connection failed (network trouble)"
    default_code = "service_unavailable"


class GatewayTimeout(APIException):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    default_detail = "Connection failed (server timeout)"
    default_code = "gateway_timeout"


class RemoteAPIException(APIException):
    def __init__(self, title, detail, code, status_code):
        super().__init__(detail, code)
        self.code = code or self.default_code
        self.default_detail = title
        self.status_code = status_code
