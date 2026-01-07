import pytest
from django.urls import NoReverseMatch, reverse
from schematools.contrib.django.models import Dataset


@pytest.mark.django_db
def test_empty_router_can_add_routes(router, gebieden_schema):
    router.initialize()
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    Dataset.create_for_schema(schema=gebieden_schema)
    router.reload()
    router_urls = [p.name for p in router.urls]
    some_expected_urls = ["gebieden-stadsdelen-list", "gebieden-v1-buurten-detail", "openapi"]
    for url in some_expected_urls:
        assert url in router_urls

    assert not router._has_model_errors()


@pytest.mark.django_db
def test_reload_add(router, bommen_dataset):
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    # Prove that the router URLs are extended on adding a model
    router.reload()
    assert len(router.urls) > 1

    # Prove that URLs can now be resolved.
    assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:bommen-v1-bommen-list")


@pytest.mark.django_db
def test_reload_delete(router, bommen_dataset):
    router.reload()
    assert len(router.urls) > 1
    assert reverse("dynamic_api:bommen-bommen-list")  # enforce importing urls.py
    assert reverse("dynamic_api:bommen-v1-bommen-list")

    # Prove that the router also unregisters the URLs
    bommen_dataset.delete()
    router.reload()
    router_urls = [p.name for p in router.urls]
    assert router_urls == ["api-root"]

    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-bommen-list")
    with pytest.raises(NoReverseMatch):
        assert reverse("dynamic_api:bommen-v1-bommen-list")


@pytest.mark.django_db
def test_router_excludes_disabled_api(settings, router, bommen_dataset, gebieden_dataset):
    router.reload()

    assert reverse("dynamic_api:bommen-bommen-list")
    assert reverse("dynamic_api:bommen-v1-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")

    bommen_dataset.enable_api = False
    bommen_dataset.save()

    router.reload()

    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:bommen-bommen-list")
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:bommen-v1-bommen-list")
    assert reverse("dynamic_api:gebieden-buurten-list")


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
