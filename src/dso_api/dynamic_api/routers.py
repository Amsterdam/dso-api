from __future__ import annotations

import logging
from typing import Dict, List, Type, TYPE_CHECKING

from django.urls import NoReverseMatch, reverse
from rest_framework import routers

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.locking import lock_for_writing
from dso_api.dynamic_api.serializers import serializer_factory
from dso_api.dynamic_api.views import viewset_factory

logger = logging.getLogger(__name__)
reload_counter = 0

if TYPE_CHECKING:
    from dso_api.dynamic_api.models import DynamicModel


class DynamicRouter(routers.SimpleRouter):
    def __init__(self):
        super().__init__(trailing_slash=True)

    def initialize(self) -> List[Type[DynamicModel]]:
        """Initialize all dynamic routes on startup."""
        tmp_router = routers.SimpleRouter()

        # Generate new viewsets for everything
        models = []
        for dataset in Dataset.objects.all():
            dataset_name = dataset.schema.id  # not dataset.name!

            for model in dataset.create_models():
                url_prefix = f'{dataset_name}/{model.get_table_id()}'
                logger.debug("Created model for %s", url_prefix)

                if dataset.enable_api:
                    models.append(model)
                    viewset = viewset_factory(model)
                    tmp_router.register(
                        prefix=url_prefix,
                        viewset=viewset,
                        basename=f"{dataset_name}-{model.get_table_id()}"
                    )

        # Atomically copy the new viewset registrations
        self.registry = tmp_router.registry

        # invalidate the urls cache
        if hasattr(self, '_urls'):
            del self._urls

        return models

    @lock_for_writing
    def reload(self) -> Dict[Type[DynamicModel], str]:
        """Regenerate all viewsets for this router."""
        from . import urls  # avoid cyclic imports

        # Clear the LRU-cache
        serializer_factory.cache_clear()

        # Note that the models get recreated too. This works as expected,
        # since each model creation flushes the App registry caches.
        models = self.initialize()

        # Refresh URLConf in urls.py
        urls.refresh_urls(self)

        # Return which models + urls were generated
        result = {}
        for model in models:
            viewname = f"dynamic_api:{model.get_dataset_id()}-{model.get_table_id()}-list"
            try:
                url = reverse(viewname)
            except NoReverseMatch as e:
                raise RuntimeError(
                    "URLConf reloading failed, unable to resolve %s", viewname
                ) from e

            result[model] = url

        return result
