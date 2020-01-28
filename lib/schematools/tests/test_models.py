from schematools.models import model_factory
from schematools.schema.types import DatasetSchema
from pathlib import Path

HERE = Path(__file__).parent


def test_models():
    dataset = DatasetSchema.from_file(HERE / "data" / "afval.json")
    table = dataset.tables[0]
    model_cls = model_factory(dataset, table)
    meta = model_cls._meta
    assert len(meta.get_fields()) == len(table["schema"]["properties"])
    assert meta.app_label == dataset.id
    breakpoint()
