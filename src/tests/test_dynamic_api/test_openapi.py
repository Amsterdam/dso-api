import pytest
from django.urls import NoReverseMatch, reverse

from dso_api.dynamic_api import openapi


@pytest.mark.django_db
def test_get_patterns(afval_dataset, fietspaaltjes_dataset, filled_router):
    """Prove that the get_dataset_patterns() generates only patterns of a particular view."""
    patterns = openapi.get_dataset_patterns("fietspaaltjes")

    # First prove that both URLs can be resolved in the app
    assert reverse("dynamic_api:afvalwegingen-containers-list")
    assert reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list")

    # Then prove that the subset patterns are not providing all URLs
    assert reverse("dynamic_api:fietspaaltjes-fietspaaltjes-list", urlconf=tuple(patterns))
    with pytest.raises(NoReverseMatch):
        reverse("dynamic_api:afvalwegingen-containers-list", urlconf=tuple(patterns))
