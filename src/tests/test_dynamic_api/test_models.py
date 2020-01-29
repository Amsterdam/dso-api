from pathlib import Path

from dso_api.lib.schematools.models import model_factory
from dso_api.lib.schematools.types import DatasetSchema

HERE = Path(__file__).parent


def test_models():
    dataset = DatasetSchema.from_file(HERE / ".." / "files" / "afval.json")
    table = dataset.tables[0]
    model_cls = model_factory(table)
    meta = model_cls._meta
    assert len(meta.get_fields()) == len(table["schema"]["properties"])
    assert meta.app_label == dataset.id
