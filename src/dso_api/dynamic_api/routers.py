import logging

from rest_framework import routers

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.serializers import serializer_factory
from dso_api.dynamic_api.views import viewset_factory

logger = logging.getLogger(__name__)


class DynamicRouter(routers.SimpleRouter):
    def __init__(self):
        super().__init__(trailing_slash=True)

    def reload(self):
        """Regenerate all viewsets for this router."""
        # Should avoid early and cyclic imports
        from . import urls

        tmp_router = routers.SimpleRouter()

        # Note that the models get recreated too. This works as expected,
        # since each model creation flushes the AppConfig caches.

        # TODO: add lock

        # Clear the LRU-cache
        serializer_factory.cache_clear()

        # Generate new viewsets for everything
        models = []
        for dataset in Dataset.objects.all():
            for model in dataset.create_models():
                models.append(model)
                viewset = viewset_factory(model)
                basename = f"{dataset.name}-{model.get_table_id()}"

                logger.debug("Creating model for %s", basename)

                tmp_router.register(
                    prefix=f'{dataset.name}/{model.get_table_id()}',
                    viewset=viewset,
                    basename=basename
                )

        # Atomically copy the new viewset registrations
        self.registry = tmp_router.registry

        # invalidate the urls cache
        if hasattr(self, '_urls'):
            del self._urls

        # Refresh URLConf in urls.py
        urls.refresh(self.urls)

        return models
