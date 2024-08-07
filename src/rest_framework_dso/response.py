"""Streaming rendering support on top of Django-Rest-Framework.

Django has the internal support for streaming responses, but REST Framework does not.
This module bridges that feature into the response format that Django-Rest-Framework's
rendering classes need.

This generic :class:`StreamingResponse` class allows responses to be submitted as streaming.
A streaming response can submit large amounts of data without consuming too much memory.
Each time a bit of the response is generated, it's immediately written to the client.

The rendered data also needs to be generated on consumption to have the full benefits of
streaming. The :class:`~rest_framework_dso.serializers.DSOListSerializer` achieves this
by returning the results as a Python generator instead of a pre-rendered list.
"""

from http.client import responses
from inspect import isgenerator

from django.http import StreamingHttpResponse
from rest_framework.response import Response


class StreamingResponse(StreamingHttpResponse):
    """A reimplementation of the DRF 'Response' class
    that provides actual streaming content.

    While it's possible to submit a generator to the DRF Response class,
    it will concatenate the results in-memory when reading
    the HttpResponse.content property.
    """

    def __init__(
        self,
        data=None,
        status=None,
        template_name=None,
        headers=None,
        exception=False,
        content_type=None,
    ):
        """Init parameters are similar to the DRF Response class."""
        # Note that StreamingHttpResponse.__init__() sets .streaming_content
        super().__init__(self._read_rendered_content(), status=status)

        # Similar to DRF Response
        self.data = data
        self.template_name = template_name
        self.exception = exception
        self.content_type = content_type

        if headers:
            for name, value in headers.items():
                self[name] = value

    @classmethod
    def from_response(cls, response: Response):
        """Convert a regular DRF Response into this streaming response.
        This is to be called from the ``APIView.finalize_response()`` function.
        """
        content_type = response.content_type

        # Make sure the content-type is properly set. Normally this happens inside
        # Response.rendered_content, but this is too late for streaming: the HTTP
        # headers are already copied before the .streaming_content generator is read.
        if content_type is None and hasattr(response, "accepted_renderer"):
            media_type = response.accepted_renderer.media_type
            charset = response.accepted_renderer.charset
            content_type = (
                f"{media_type}; charset={charset}" if charset else media_type  # noqa: E702
            )  # noqa: E702
            response["Content-Type"] = content_type

        streaming_response = cls(
            response.data,
            status=response.status_code,
            template_name=response.template_name,
            headers=dict(response.items()),
            content_type=content_type,
        )

        # Copy DRF attributes from finalize_response()
        if hasattr(response, "accepted_renderer"):
            streaming_response.accepted_renderer = response.accepted_renderer
            streaming_response.accepted_media_type = response.accepted_media_type
            streaming_response.renderer_context = response.renderer_context

        return streaming_response

    def _read_rendered_content(self):
        """Wrap the retrieval of the stream data. This is applied to self.streaming_content."""
        # Calling the original DRF Response.rendered_content is sufficient, it
        # can read all attributes from this class and produce the stream.
        stream = Response.rendered_content.__get__(self)
        if not isgenerator(stream):
            raise RuntimeError(
                f"No stream generated by {self.accepted_renderer.__class__.__name__}"
            )

        try:
            yield from stream
        except Exception as e:  # noqa: B902
            yield self.render_exception(e)
            raise  # stops the server rendering

    def render_exception(self, exception):
        """Render an exception message in case the stream rendering fails.
        Otherwise, the response just closes and the client may assume it received the whole file.
        The actual exception is still raised and logged server-side.
        """
        # Allow to delegate the rendering to the accepted renderer
        renderer = getattr(self.accepted_renderer, "render_exception", None)
        if renderer is not None:
            return renderer(exception)
        else:
            return "\nAborted by internal server error.\n"  # Default message

    @property
    def status_text(self):
        """Copied from DRF Response class"""
        return responses.get(self.status_code, "")

    def __getstate__(self):
        """Copied from DRF Response class.
        Remove attributes from the response that shouldn't be cached.
        """
        state = super().__getstate__()
        for key in (
            "accepted_renderer",
            "renderer_context",
            "resolver_match",
            "client",
            "request",
            "json",
            "wsgi_request",
        ):
            if key in state:
                del state[key]
        state["_closable_objects"] = []
        return state
