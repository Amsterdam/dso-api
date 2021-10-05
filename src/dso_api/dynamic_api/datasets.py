from django.conf import settings
from django.db.models import Q
from schematools.contrib.django.managers import DatasetQuerySet
from schematools.contrib.django.models import Dataset


def get_active_datasets(queryset=None) -> DatasetQuerySet:
    """Get published datasets:
    Get all datasets that should be published.
    - remove Non-default datasets
    - include only datasets defined in DATASETS_LIST (if settings.DATASETS_LIST is defined)
    - exclude any datasets in DATASETS_EXCLUDE list (if settings.DATASETS_EXCLUDE is defined)
    """
    if queryset is None:
        queryset = Dataset.objects
    queryset = queryset.filter(Q(version=None) | Q(is_default_version=True))

    if settings.DATASETS_LIST is not None:
        queryset = queryset.filter(name__in=settings.DATASETS_LIST)
    if settings.DATASETS_EXCLUDE is not None:
        queryset = queryset.exclude(name__in=settings.DATASETS_EXCLUDE)
    return queryset
