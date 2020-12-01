from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Type

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.urls import NoReverseMatch, reverse
from rest_framework import routers

from schematools.contrib.django.models import Dataset
from schematools.utils import to_snake_case

from dso_api.dynamic_api.app_config import register_model, add_custom_serializers
from dso_api.dynamic_api.locking import lock_for_writing
from dso_api.dynamic_api.oas3 import get_openapi_json_view
from dso_api.dynamic_api.remote import remote_serializer_factory, remote_viewset_factory
from dso_api.dynamic_api.serializers import get_view_name, serializer_factory
from dso_api.dynamic_api.views import viewset_factory

logger = logging.getLogger(__name__)
reload_counter = 0

if TYPE_CHECKING:
    from schematools.contrib.django.models import DynamicModel


class DynamicRouter(routers.DefaultRouter):
    """Router that dynamically creates all viewsets based on the Dataset models."""

    include_format_suffixes = False

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.all_models = {}
        self.static_routes = []

    def get_api_root_view(self, api_urls=None):
        return get_openapi_json_view()

    def initialize(self):
        """Initialize all dynamic routes on startup."""
        if not settings.INITIALIZE_DYNAMIC_VIEWSETS:
            return []

        if Dataset._meta.db_table not in connection.introspection.table_names():
            # There are no tables, so no routes to initialize.
            # This avoids a startup error for manage.py migrate
            return []

        self._initialize_viewsets()

    def register(self, prefix, viewset, basename=None):
        """Preserve any manually added routes on reloading"""
        super().register(prefix, viewset, basename=basename)
        self.static_routes.append(self.registry[-1])

    def _initialize_viewsets(self) -> List[Type[DynamicModel]]:
        """Build all viewsets, serializers, models and URL routes."""
        # Generate new viewsets for everything
        dataset_routes, generated_models = self._build_db_viewsets()
        remote_routes = self._build_remote_viewsets()

        # Atomically copy the new viewset registrations
        self.registry = self.static_routes + dataset_routes + remote_routes

        # invalidate the urls cache
        if hasattr(self, "_urls"):
            del self._urls

        return generated_models

    def _build_db_viewsets(self):
        """Initialize viewsets that are linked to Django database models."""
        tmp_router = routers.SimpleRouter()
        generated_models = []

        add_custom_serializers()
        datasets = {}
        for dataset in Dataset.objects.db_enabled():  # type: Dataset
            dataset_id = dataset.schema.id  # not dataset.name!
            datasets[dataset_id] = dataset
            new_models = {}

            for model in dataset.create_models():
                logger.debug("Created model %s.%s", dataset_id, model.__name__)

                # Register model in Django apps under Datasets application name,
                #  because django requires fully set up app for model discovery to work.
                register_model(dataset, model)

                if dataset.enable_api:
                    new_models[model._meta.model_name] = model

            self.all_models[dataset_id] = new_models
            generated_models.extend(new_models.values())

        # Generate views now that all models have been created.
        # This makes sure the 'to' field is resolved to an actual model class.
        for app_label, models_by_name in self.all_models.items():
            for model in models_by_name.values():
                if model.has_parent_table():
                    # Do not create separate viewsets for nested tables.
                    continue

                dataset_id = model.get_dataset_id()
                dataset = datasets[dataset_id]

                # Determine the URL prefix for the model
                url_prefix = self.make_url(
                    dataset.url_prefix, dataset_id, model.get_table_id()
                )

                logger.debug("Created viewset %s", url_prefix)
                viewset = viewset_factory(model)
                table_id = to_snake_case(model.get_table_id())
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{dataset_id}-{table_id}",
                )

        return tmp_router.registry, generated_models

    def _build_remote_viewsets(self):
        """Initialize viewsets that are are proxies for remote URLs"""
        tmp_router = routers.SimpleRouter()

        for dataset in Dataset.objects.endpoint_enabled():  # type: Dataset
            schema = dataset.schema
            dataset_id = schema.id

            for table in schema.tables:
                # Determine the URL prefix for the model
                url_prefix = self.make_url(dataset.url_prefix, dataset_id, table.id)
                serializer_class = remote_serializer_factory(table)
                viewset = remote_viewset_factory(
                    endpoint_url=dataset.endpoint_url,
                    serializer_class=serializer_class,
                    dataset_id=dataset_id,
                    table_id=table.id,
                    table_schema=table,
                )
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{to_snake_case(dataset_id)}-{to_snake_case(table.id)}",
                )

        return tmp_router.registry

    def make_url(self, prefix, *parts):
        """Generate the URL for the viewset"""
        parts = [to_snake_case(part) for part in parts]

        url_path = "/".join(parts)

        # Allow to add a prefix
        prefix = prefix.strip("/")  # extra strip for safety
        if prefix:
            url_path = f"{prefix}/{url_path}"

        return url_path

    @lock_for_writing
    def reload(self) -> Dict[Type[DynamicModel], str]:
        """Regenerate all viewsets for this router."""
        from . import urls  # avoid cyclic imports

        old_dynamic_apps = set(self.all_models.keys())

        # Clear caches
        serializer_factory.cache_clear()
        self.all_models.clear()

        # Clear models from the Django App registry cache for removed apps
        self._prune_app_registry(old_dynamic_apps)

        # Note that the models get recreated too. This works as expected,
        # since each model creation flushes the App registry caches.
        models = self._initialize_viewsets()

        # Refresh URLConf in urls.py
        urls.refresh_urls(self)

        # Return which models + urls were generated
        result = {}
        for model in models:
            if model.has_parent_table():
                # Do not create separate viewsets for nested tables.
                continue
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
