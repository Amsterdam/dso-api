from django.conf import settings
from schematools.contrib.django.managers import DatasetQuerySet
from schematools.contrib.django.models import Dataset


def get_active_datasets(queryset=None, api_enabled=True) -> DatasetQuerySet:
    """Get published datasets:

    Get all datasets that should be published.
    - include only datasets defined in DATASETS_LIST (if settings.DATASETS_LIST is defined)
    - exclude any datasets in DATASETS_EXCLUDE list (if settings.DATASETS_EXCLUDE is defined)
    """
    if queryset is None:
        queryset = Dataset.objects

    if settings.DATASETS_LIST is not None:
        queryset = queryset.filter(name__in=settings.DATASETS_LIST)
    if settings.DATASETS_EXCLUDE is not None:
        queryset = queryset.exclude(name__in=settings.DATASETS_EXCLUDE)

    # By default only return datasets that have an API enabled,
    # unless this is explicitly left out.
    if api_enabled:
        queryset = queryset.api_enabled()

    return queryset
