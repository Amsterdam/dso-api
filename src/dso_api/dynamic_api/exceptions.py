from django.http import JsonResponse
from rest_framework import status

W3HTMLREF = "https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.5.1"


def _get_unique_trace_id(request):
    unique_id = request.META.get(
        "HTTP_X_UNIQUE_ID"
    )  # X-Unique-ID wordt in haproxy gezet
    if unique_id:
        instance = f"unique_id:{unique_id}"
    else:
        instance = request.build_absolute_uri()
    return instance


def server_error(request, *args, **kwargs):
    """
    Generic 500 error handler.
    """
    data = {
        "type": f"{W3HTMLREF} 500 Server Error",
        "title": "Server Error (500)",
        "detail": "",
        "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "instance": _get_unique_trace_id(request),
    }
    return JsonResponse(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def bad_request(request, exception, *args, **kwargs):
    """
    Generic 400 error handler.
    """
    data = {
        "type": f"{W3HTMLREF} 400 Bad Request",
        "title": "Bad Request (400)",
        "detail": "",
        "status": status.HTTP_400_BAD_REQUEST,
        "instance": _get_unique_trace_id(request),
    }
    return JsonResponse(data, status=status.HTTP_400_BAD_REQUEST)


def not_found(request, exception, *args, **kwargs):
    """
    Generic 404 error handler.
    """
    data = {
        "type": f"{W3HTMLREF} 404 Not Found",
        "title": "Not Found (404)",
        "detail": "",
        "status": status.HTTP_404_NOT_FOUND,
        "instance": _get_unique_trace_id(request),
    }
    return JsonResponse(data, status=status.HTTP_404_NOT_FOUND)
