import pytest

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.urls import router


@pytest.mark.django_db
def test_reload_add(bommen_schema_json):
    assert len(router.urls) == 0, [p.name for p in router.urls]

    Dataset.objects.create(name="bommen", schema_data=bommen_schema_json)
    router.reload()

    assert len(router.urls) > 0
