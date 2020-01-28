import pytest
from django.urls import NoReverseMatch, reverse

from dso_api.dynamic_api.urls import router


@pytest.mark.django_db
def test_reload_add(bommen_dataset):
    assert len(router.urls) == 0, [p.name for p in router.urls]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 0

    # Prove that URLs can now be resolved.
    assert reverse('dynamic_api:bommen-bommen-list')


@pytest.mark.django_db
def test_reload_delete(bommen_dataset):
    router.reload()
    assert len(router.urls) > 0

    # Prove that the router also unregisters the URLs
    bommen_dataset.delete()
    router.reload()
    assert len(router.urls) == 0

    with pytest.raises(NoReverseMatch):
        assert reverse('dynamic_api:bommen-bommen-list')
