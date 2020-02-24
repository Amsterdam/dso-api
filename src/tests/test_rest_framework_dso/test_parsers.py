from io import BytesIO

from pytest import raises

from rest_framework_dso.crs import RD_NEW
from rest_framework_dso.exceptions import PreconditionFailed
from rest_framework_dso.parsers import DSOJsonParser


class MockedView:
    def __init__(self, request):
        self.request = request


class TestDSOJsonParser:
    """Prove that the DSO JSON Parser works"""

    def test_missing_value(self, api_request):
        """Prove that missing values are cought"""
        parser = DSOJsonParser()
        with raises(PreconditionFailed):
            parser.parse(BytesIO(), parser_context={"view": MockedView(api_request)})

    def test_json_dict(self, api_request):
        """Prove that dict data can be parsed"""
        api_request.META["HTTP_CONTENT_CRS"] = "EPSG:28992"
        parser = DSOJsonParser()
        data = parser.parse(
            BytesIO(b'{"data": 123}'), parser_context={"view": MockedView(api_request)}
        )

        assert isinstance(data, dict)
        assert data.crs == RD_NEW

    def test_json_list(self, api_request):
        """Prove that list data can be parsed"""
        api_request.META["HTTP_CONTENT_CRS"] = "EPSG:28992"
        parser = DSOJsonParser()
        data = parser.parse(
            BytesIO(b"[123, 456]"), parser_context={"view": MockedView(api_request)}
        )

        assert isinstance(data, list)
        assert data.crs == RD_NEW
