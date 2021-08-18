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


@pytest.mark.django_db
def test_only_selected_datasets_loaded(
    settings, router, bommen_dataset, gebieden_dataset, meldingen_dataset
):
    router.reload()

    # Bommen dataset reverse works, as dataset is registered
    assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")
    assert reverse("dynamic_api:meldingen-statistieken-list")

    settings.DATASETS_LIST = ["gebieden", "meldingen"]

    router.reload()
    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")
    assert reverse("dynamic_api:meldingen-statistieken-list")


@pytest.mark.django_db
def test_router_excludes_datasets(
    settings, router, bommen_dataset, gebieden_dataset, meldingen_dataset
):
    router.reload()

    # Bommen dataset reverse works, as dataset is registered
    assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")
    assert reverse("dynamic_api:meldingen-statistieken-list")

    settings.DATASETS_EXCLUDE = ["bommen"]

    router.reload()
    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")
    assert reverse("dynamic_api:meldingen-statistieken-list")


@pytest.mark.django_db
def test_router_excludes_datasets_combined_with_list(
    settings, router, bommen_dataset, gebieden_dataset, meldingen_dataset
):
    router.reload()

    # Bommen dataset reverse works, as dataset is registered
    assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")
    assert reverse("dynamic_api:meldingen-statistieken-list")

    settings.DATASETS_LIST = ["gebieden", "bommen"]
    settings.DATASETS_EXCLUDE = ["bommen"]

    router.reload()

    assert reverse("dynamic_api:gebieden-buurten-list")
    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")
    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:meldingen-statistieken-list")


@pytest.mark.django_db
def test_router_excludes_non_default_dataset_versions(settings, bommen_v2_dataset, router):
    # Not using filled_router here, as it will throw RuntimeError,
    #  due to missing model, which is expected,
    #  because non-default dataset is not expected to be registered in router.
    router.reload()
    assert len(router.urls) == 1
    assert router.all_models == {}

    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")


@pytest.mark.django_db
def test_router_creates_views_on_subpaths(
    settings, router, fietspaaltjes_dataset_subpath, afval_dataset_subpath
):
    router.reload()

    # Datasets on subpaths are registered
    assert reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")
    assert reverse("dynamic_api:afvalwegingen-containers-list")

    # Indexviews are registered on the subpaths
    assert reverse("dynamic_api:sub-index")
    assert reverse("dynamic_api:sub/path-index")
