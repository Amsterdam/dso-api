from rest_framework.views import exception_handler as drf_exception_handler


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
