from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Type

from django.apps import apps
from django.db import connection
from django.urls import NoReverseMatch, reverse
from django.conf import settings
from rest_framework import routers

from dso_api.datasets.models import Dataset
from dso_api.dynamic_api.locking import lock_for_writing
from dso_api.dynamic_api.serializers import serializer_factory, get_view_name
from dso_api.dynamic_api.views import DynamicAPIRootView, viewset_factory

logger = logging.getLogger(__name__)
reload_counter = 0

if TYPE_CHECKING:
    from dso_api.lib.schematools.models import DynamicModel


class DynamicRouter(routers.DefaultRouter):
    """Router that dynamically creates all viewsets based on the Dataset models."""

    #: Override root view to add description
    APIRootView = DynamicAPIRootView

    include_format_suffixes = False

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.all_models = {}

    def initialize(self):
        """Initialize all dynamic routes on startup."""
        if not settings.INITIALIZE_DYNAMIC_VIEWSETS:
            return []

        if Dataset._meta.db_table not in connection.introspection.table_names():
            # There are no tables, so no routes to initialize.
            # This avoids a startup error for manage.py migrate
            return []

        self._initialize_viewsets()

    def _initialize_viewsets(self) -> List[Type[DynamicModel]]:
        """Build all viewsets, serializers, models and URL routes."""
        tmp_router = routers.SimpleRouter()
        generated_models = []

        # Generate new viewsets for everything
        for dataset in Dataset.objects.all():
            dataset_name = dataset.schema.id  # not dataset.name!
            new_models = {}

            for model in dataset.create_models():
                logger.debug("Created model %s.%s", dataset_name, model.__name__)

                if dataset.enable_api:
                    new_models[model._meta.model_name] = model

            self.all_models[dataset_name] = new_models
            generated_models.extend(new_models.values())

        # Generate views now that all models have been created.
        # This makes sure the 'to' field is resolved to an actual model class.
        for app_label, models_by_name in self.all_models.items():
            for model in models_by_name.values():
                if model._table_schema.get("schema", {}).get("parentTable") is not None:
                    # Do not create separate viewsets for nested tables.
                    continue
                dataset_name = model.get_dataset_id()
                url_prefix = f"{dataset_name}/{model.get_table_id()}"
                logger.debug("Created viewset %s", url_prefix)

                viewset = viewset_factory(model)
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{dataset_name}-{model.get_table_id()}",
                )

        # Atomically copy the new viewset registrations
        self.registry = tmp_router.registry

        # invalidate the urls cache
        if hasattr(self, "_urls"):
            del self._urls

        return generated_models

    @lock_for_writing
    def reload(self) -> Dict[Type[DynamicModel], str]:
        """Regenerate all viewsets for this router."""
        from . import urls  # avoid cyclic imports

        old_dynamic_apps = set(self.all_models.keys())

        # Clear caches
        serializer_factory.cache_clear()
        self.all_models.clear()

        # Note that the models get recreated too. This works as expected,
        # since each model creation flushes the App registry caches.
        models = self._initialize_viewsets()

        # Clear models from the Django App registry cache for removed apps
        self._prune_app_registry(old_dynamic_apps)

        # Refresh URLConf in urls.py
        urls.refresh_urls(self)

        # Return which models + urls were generated
        result = {}
        for model in models:
            viewname = get_view_name(model, "list")
            try:
                url = reverse(viewname)
            except NoReverseMatch as e:
                raise RuntimeError(
                    "URLConf reloading failed, unable to resolve %s", viewname
                ) from e

            result[model] = url

        return result

    @lock_for_writing
    def clear_urls(self):
        """Internal function for tests, restore the internal registry."""
        from . import urls  # avoid cyclic imports

        old_dynamic_apps = set(self.all_models.keys())
        self.registry = []
        self.all_models = {}
        self._prune_app_registry(old_dynamic_apps)

        # invalidate the urls cache
        if hasattr(self, "_urls"):
            del self._urls

        # Clear the LRU-cache
        serializer_factory.cache_clear()

        # Refresh URLConf in urls.py
        urls.refresh_urls(self)

    def _prune_app_registry(self, old_dynamic_apps: set):
        """Clear models from the Django App registry cache if they are no longer used."""
        for removed_app in old_dynamic_apps - set(self.all_models.keys()):
            del apps.all_models[removed_app]
