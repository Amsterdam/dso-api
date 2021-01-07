from io import BytesIO

from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_csv.renderers import CSVStreamingRenderer

from rest_framework_dso.serializer_helpers import ReturnGenerator


class DynamicCSVRenderer(CSVStreamingRenderer):
    """Overwritten CSV renderer to provide proper headers.

    In the view methods (e.g. ``get_renderer_context()``), the serializer
    layout is not accessible. Hence the header is reformatted within a custom
    output renderer.
    """

    def render(self, data, media_type=None, renderer_context=None):
        if isinstance(data, ReturnDict):
            serializer = data.serializer
        elif isinstance(data, (ReturnList, ReturnGenerator)):
            serializer = data.serializer.child
        else:
            serializer = None

        if serializer is not None:
            # Serializer type is known, introduce better CSV header column.
            renderer_context = {
                **(renderer_context or {}),
                "header": [
                    name
                    for name, field in serializer.fields.items()
                    if name != "schema"
                    and not isinstance(field, HyperlinkedRelatedField)
                ],
                "labels": {
                    name: field.label for name, field in serializer.fields.items()
                },
            }

        output = super().render(
            data, media_type=media_type, renderer_context=renderer_context
        )

        # This method must have a "yield" statement so finalize_response() can
        # recognize this renderer returns a generator/stream, and patch the
        # response.streaming attribute accordingly.
        yield from _chunked_output(output)


def _chunked_output(stream, chunk_size=4096):
    """Output in larger chunks to avoid many small writes or back-forth calls
    between the WSGI server write code and the original generator function.
    Inspired by django-gisserver logic which applies the same trick.
    """
    buffer = BytesIO()
    buffer_size = 0
    for row in stream:
        buffer.write(row)
        buffer_size += len(row)

        if buffer_size > chunk_size:
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            buffer_size = 0

    if buffer_size:
        yield buffer.getvalue()
