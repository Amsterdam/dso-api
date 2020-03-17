import pytest
from django.urls import NoReverseMatch, reverse


@pytest.mark.django_db
def test_reload_add(router, bommen_dataset):
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 1

    # Prove that URLs can now be resolved.
    assert reverse("dynamic_api:bommen-bommen-list")


@pytest.mark.django_db
def test_reload_delete(router, bommen_dataset):
    router.reload()
    assert len(router.urls) > 1
    assert reverse("dynamic_api:bommen-bommen-list")  # enforce importing urls.py

    # Prove that the router also unregisters the URLs
    bommen_dataset.delete()
    router.reload()
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")
