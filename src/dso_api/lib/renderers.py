from rest_framework.renderers import BrowsableAPIRenderer

from rest_framework_dso.renderers import RendererMixin


class PatchedBrowsableAPIRenderer(RendererMixin, BrowsableAPIRenderer):
    def get_context(self, data, accepted_media_type, renderer_context):
        context = super().get_context(data, accepted_media_type, renderer_context)

        # Fix response content-type when it's filled in by the exception_handler
        response = renderer_context["response"]
        if response.content_type:
            context["response_headers"]["Content-Type"] = response.content_type

        return context

    def render(self, data, accepted_media_type=None, renderer_context=None):
        ret = super().render(
            data,
            accepted_media_type=accepted_media_type,
            renderer_context=renderer_context,
        )

        # Make sure the browsable API always returns text/html
        # by default it falls back to the current media,
        # unless the response (e.g. exception_handler) has overwritten the type.
        response = renderer_context["response"]
        response["content-type"] = "text/html; charset=utf-8"
        return ret
