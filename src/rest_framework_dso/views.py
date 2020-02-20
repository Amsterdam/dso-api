from typing import Union

from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Return the exceptions as 'application/problem+json'.

    See: https://tools.ietf.org/html/rfc7807
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        # response.data are the fields
        response.data = {
            "type": f"urn:apiexception:{exc.default_code}",
            "detail": str(exc.default_detail),
            "status": response.status_code,
            "invalid-params": get_invalid_params(exc, exc.detail),
            # Also include the whole tree of recursive errors that DRF generates
            "x-validation-errors": response.data,
        }

        response.content_type = "application/problem+json"
    elif "detail" in response.data:
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
    else:
        response.content_type = "application/json"  # Avoid being hal-json

    return response


def get_invalid_params(
    exc: ValidationError, detail: Union[ErrorDetail, dict, list], field_name=None
) -> list:
    """Flatten the entire chain of DRF messages.
    This can be a recursive tree for POST requests with complex serializer data.
    """
    result = []
    if isinstance(detail, dict):
        for name, errors in detail.items():
            full_name = f"{field_name}.{name}" if field_name else name
            result.extend(get_invalid_params(exc, errors, field_name=full_name))
    elif isinstance(detail, list):
        for i, error in enumerate(detail):
            full_name = f"{field_name}[{i}]" if isinstance(error, dict) else field_name
            result.extend(get_invalid_params(exc, error, field_name=full_name))
    elif isinstance(detail, ErrorDetail):
        if field_name is None:
            field_name = detail.code
        # flattened is now RFC7807 mandates it
        result.append(
            {
                "type": f"urn:apiexception:{exc.default_code}:{detail.code}",
                "name": field_name,
                "reason": str(detail),
            }
        )
    else:
        raise TypeError(f"Invalid value for _get_invalid_params(): {detail!r}")

    return result
