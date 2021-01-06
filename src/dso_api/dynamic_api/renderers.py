from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList
from rest_framework_csv.renderers import CSVStreamingRenderer


class DynamicCSVRenderer(CSVStreamingRenderer):
    """Overwritten CSV renderer to provide proper headers.

    In the view methods (e.g. ``get_renderer_context()``), the serializer
    layout is not accessible. Hence the header is reformatted within a custom
    output renderer.
    """

    def render(self, data, media_type=None, renderer_context=None):
        if isinstance(data, ReturnDict):
            serializer = data.serializer
        elif isinstance(data, ReturnList):
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

        return super().render(
            data, media_type=media_type, renderer_context=renderer_context
        )
