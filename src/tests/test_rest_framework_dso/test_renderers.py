import inspect

import pytest

from rest_framework_dso.renderers import CSVRenderer, GeoJSONRenderer, HALJSONRenderer
from rest_framework_dso.response import StreamingResponse


class TestRenderer:
    """Perform some in-depth feature tests of the rendering classes"""

    def test_csv_rendering(self):
        """Prove that the renderer works"""
        renderer = CSVRenderer()
        output = renderer.render(
            data=[
                {"foo": "1", "bar": "2"},
                {"foo": "3", "bar": "4"},
            ],
            renderer_context={"header": ["foo", "bar"]},
        )

        # Instead of directly rendering, the renderer should produce an generator
        assert inspect.isgenerator(output)

        data = b"".join(output)
        assert data == b"foo,bar\r\n1,2\r\n3,4\r\n"

    RENDERERS = {
        "csv": (
            CSVRenderer,
            [b"foo,bar\r\n", b"1,2\r\n", b"\n\nAborted by RuntimeError during rendering!\n"],
        ),
        "json": (
            HALJSONRenderer,
            [b'[\n  {"foo":"1","bar":"2"}', b"/* Aborted by RuntimeError during rendering! */\n"],
        ),
        "geojson": (
            GeoJSONRenderer,
            [
                b'{"type":"FeatureCollection"',
                b',\n  "features": [\n    ',
                b'{"type":"Feature","properties":{"foo":"1","bar":"2"}}',
                b"/* Aborted by RuntimeError during rendering! */\n",
            ],
        ),
    }

    @pytest.mark.parametrize("format", list(RENDERERS.keys()))
    def test_exception_rendering(self, format):
        """Prove that aborted streams produce an exception as final response data.
        The StreamingResponse makes sure the stream doesn't just abort without errors.
        It renders an exception after
        """
        renderer_class, expected_data = self.RENDERERS[format]

        def _data_generator():
            yield {"foo": "1", "bar": "2"}
            raise RuntimeError("TEST EXCEPTION")

        response = StreamingResponse(data=_data_generator())
        response.accepted_renderer = renderer_class()
        response.accepted_media_type = response.accepted_renderer.media_type
        response.renderer_context = {
            "header": ["foo", "bar"],  # for CSVRenderer
        }

        # make sure buffers are directly flushed for testing
        # Otherwise parts of the output are not included in 'blocks'
        response.accepted_renderer.chunk_size = 1

        # Read the response in chunks, as if a client is processing it.
        blocks = []
        with pytest.raises(RuntimeError):
            for data in response:
                blocks.append(data)

        # The first part of the response should be received.
        assert blocks == expected_data
