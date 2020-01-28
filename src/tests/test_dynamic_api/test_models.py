from dso_api.dynamic_api.models import model_factory
from dso_api.datasets.types import DatasetSchema
from pathlib import Path

HERE = Path(__file__).parent


def test_models():
    dataset = DatasetSchema.from_file(HERE / ".." / "files" / "afval.json")
    table = dataset.tables[0]
    model_cls = model_factory(table)
    meta = model_cls._meta
    assert len(meta.get_fields()) == len(table["schema"]["properties"])
    assert meta.app_label == dataset.id
