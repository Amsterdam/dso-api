from rest_framework import exceptions
from rest_framework import status


class PreconditionFailed(exceptions.APIException):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_code = "precondition_failed"
