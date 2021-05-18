"""The router logic is the core of the dynamic API creation.

When the call to :func:`~DynamicRouter.initialize` is made,
all viewsets, models, serializers, filtersets and so on are created.
This fills the complete router so calling :attr:`router.urls <DynamicRouter.urls>`
returns all endpoints as if they were hard-coded. The router can be used in the ``urls.py`` file
like:

.. code-block:: python

    router = DynamicRouter()
    router.initialize()

    urlpatterns = [
        path("/some/path/", include(router.urls)),
    ]

The :func:`~DynamicRouter.initialize` function is also responsible for calling
the :func:`~schematools.contrib.django.factories.model_factory`,
:func:`~dso_api.dynamic_api.views.viewset_factory` and
:func:`~dso_api.dynamic_api.remote.remote_viewset_factory` functions.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Iterable, List, Type

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.urls import NoReverseMatch, URLPattern, path, reverse
from rest_framework import routers
from rest_framework.response import Response
from rest_framework.views import APIView
from schematools.contrib.django.factories import remove_dynamic_models
from schematools.contrib.django.models import Dataset
from schematools.utils import to_snake_case

from dso_api.dynamic_api.locking import lock_for_writing
from dso_api.dynamic_api.openapi import get_openapi_json_view
from dso_api.dynamic_api.remote import remote_serializer_factory, remote_viewset_factory
from dso_api.dynamic_api.serializers import get_view_name, serializer_factory
from dso_api.dynamic_api.views import viewset_factory
from dso_api.dynamic_api.views.wfs import dataset_has_geometry_fields

logger = logging.getLogger(__name__)
reload_counter = 0

if TYPE_CHECKING:
    from schematools.contrib.django.models import DynamicModel


class DynamicAPIRootView(APIView):
    """An overview of API endpoints."""

    name = "DSO-API"  # for browsable API.
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
    )
    schema = None  # exclude from schema
    dataset_ids: List[str] = []  # set by as_view()

    def get(self, request, *args, **kwargs):
        base = request.build_absolute_uri("/").rstrip("/")
        return Response(
            {
                "datasets": {
                    ds.schema.id: {
                        "id": ds.schema.id,
                        "name": ds.name,
                        "title": ds.schema.get("title", ""),
                        "status": ds.schema.get("status", "Beschikbaar"),
                        "description": ds.schema.get("description", ""),
                        "api_type": "rest_json",
                        "api_url": base + reverse(f"dynamic_api:openapi-{ds.schema.id}"),
                        "documentation_url": base + f"/v1/docs/datasets/{ds.schema.id}.html",
                        "specification_url": base
                        + reverse("dynamic_api:swagger-ui", kwargs={"dataset_name": ds.name}),
                        "terms_of_use": {
                            "government_only": "auth" in ds.schema,
                            "pay_per_use": False,
                            "license": ds.schema.get("license", "CC0 1.0 Universal"),
                        },
                        "related_apis": (
                            [
                                {
                                    "type": "wfs",
                                    "url": base
                                    + reverse("dynamic_api:wfs", kwargs={"dataset_name": ds.name}),
                                },
                                {"type": "tiles", "url": base + reverse("dynamic_api:mvt-index")},
                            ],
                            [],
                        )[dataset_has_geometry_fields(ds)],
                    }
                    for ds in list(Dataset.objects.filter(id__in=self.dataset_ids))
                }
            }
        )


class DynamicRouter(routers.DefaultRouter):
    """Router that dynamically creates all viewsets based on the Dataset models."""

    include_format_suffixes = False

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.all_models = {}
        self.static_routes = []
        self._openapi_urls = []
        self._dataset_ids = []

    def get_api_root_view(self, api_urls=None):
        """Show the OpenAPI specification as root view."""
        return DynamicAPIRootView.as_view(dataset_ids=sorted(self._dataset_ids))

    def is_initialized(self) -> bool:
        """Tell whether the router initialization was used to create viewsets."""
        return len(self.registry) > len(self.static_routes)

    def initialize(self):
        """Initialize all dynamic routes on startup.

        The initialization is skipped when
        :ref:`INITIALIZE_DYNAMIC_VIEWSETS <INITIALIZE_DYNAMIC_VIEWSETS>` is set,
        or when the meta tables are not found in the database (e.g. using a first migrate).

        The initialization calls
        the :func:`~schematools.contrib.django.factories.model_factory`,
        :func:`~dso_api.dynamic_api.views.viewset_factory` and
        :func:`~dso_api.dynamic_api.remote.remote_viewset_factory` functions.
        """
        if not settings.INITIALIZE_DYNAMIC_VIEWSETS:
            return []

        if Dataset._meta.db_table not in connection.introspection.table_names():
            # There are no tables, so no routes to initialize.
            # This avoids a startup error for manage.py migrate
            return []

        self._initialize_viewsets()

    def get_urls(self):
        """Add extra URLs beside the registered viewsets."""
        return super().get_urls() + self._openapi_urls

    def register(self, prefix, viewset, basename=None):
        """Overwritten function to preserve any manually added routes on reloading."""
        super().register(prefix, viewset, basename=basename)
        self.static_routes.append(self.registry[-1])

    def _initialize_viewsets(self) -> List[Type[DynamicModel]]:
        """Build all viewsets, serializers, models and URL routes."""
        # Generate new viewsets for dynamic models
        serializer_factory.cache_clear()  # Avoid old cached data
        db_datasets = list(self.filter_datasets(Dataset.objects.db_enabled()))
        generated_models = self._build_db_models(db_datasets)
        dataset_routes = self._build_db_viewsets(db_datasets)

        # Same for remote API's
        api_datasets = list(self.filter_datasets(Dataset.objects.endpoint_enabled()))
        remote_routes = self._build_remote_viewsets(api_datasets)

        # OpenAPI views
        openapi_urls = self._build_openapi_views(db_datasets + api_datasets)

        # Atomically copy the new viewset registrations
        self.registry = self.static_routes + dataset_routes + remote_routes
        self._openapi_urls = openapi_urls
        self._dataset_ids = [ds.id for ds in db_datasets + api_datasets]

        # invalidate the urls cache
        if hasattr(self, "_urls"):
            del self._urls

        return generated_models

    def _build_db_models(self, db_datasets: Iterable[Dataset]) -> List[Type[DynamicModel]]:
        """Generate the Django models based on the dataset definitions."""
        generated_models = []

        # Because dataset are related, we need to 'prewarm'
        # the datatasets cache (in schematools)
        for dataset in db_datasets:
            dataset.schema

        for dataset in db_datasets:  # type: Dataset
            dataset_id = dataset.schema.id  # not dataset.name!
            new_models = {}

            for model in dataset.create_models(base_app_name="dso_api.dynamic_api"):
                logger.debug("Created model %s.%s", dataset_id, model.__name__)
                if dataset.enable_api:
                    new_models[model._meta.model_name] = model

            self.all_models[dataset_id] = new_models

            generated_models.extend(new_models.values())

        return generated_models

    def _build_db_viewsets(self, db_datasets: Iterable[Dataset]):
        """Initialize viewsets that are linked to Django database models."""
        tmp_router = routers.SimpleRouter()
        db_datasets = {dataset.schema.id: dataset for dataset in db_datasets}

        # Generate views now that all models have been created.
        # This makes sure the 'to' field is resolved to an actual model class.
        for app_label, models_by_name in self.all_models.items():
            for model in models_by_name.values():
                if model.has_parent_table():
                    # Do not create separate viewsets for nested tables.
                    continue

                dataset_id = model.get_dataset_id()
                dataset = db_datasets[dataset_id]

                # Determine the URL prefix for the model
                url_prefix = self.make_url(dataset.url_prefix, dataset_id, model.get_table_id())

                logger.debug("Created viewset %s", url_prefix)
                viewset = viewset_factory(model)
                table_id = to_snake_case(model.get_table_id())
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{dataset_id}-{table_id}",
                )

        return tmp_router.registry

    def _build_remote_viewsets(self, api_datasets: Iterable[Dataset]):
        """Initialize viewsets that are are proxies for remote URLs"""
        tmp_router = routers.SimpleRouter()

        for dataset in api_datasets:
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

    def _build_openapi_views(self, datasets: Iterable[Dataset]) -> List[URLPattern]:
        """Build the OpenAPI viewsets per dataset"""
        results = []
        for dataset in datasets:
            dataset_id = dataset.schema.id
            results.append(
                path(
                    self.make_url(dataset.url_prefix, dataset_id) + "/",
                    get_openapi_json_view(dataset_id),
                    name=f"openapi-{dataset_id}",
                )
            )
        return results

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

        # Remove all created objects, and recreate them
        # Note that the models get recreated too. This works as expected,
        # since each model creation flushes the App registry caches.
        self._delete_created_objects()
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

        # Clear all caches
        self._delete_created_objects()

        # Refresh URLConf in urls.py
        urls.refresh_urls(self)

    def _delete_created_objects(self):
        """Remove all created objects from the application memory."""
        # Clear URLs and routes
        self.registry = self.static_routes.copy()
        self._openapi_urls.clear()
        self._dataset_ids.clear()
        if hasattr(self, "_urls"):
            del self._urls

        # Clear models, serializers and app registries
        self.all_models.clear()
        serializer_factory.cache_clear()
        remove_dynamic_models()

    def filter_datasets(self, queryset):
        """Filter datasets:
        - remove Non-default datasets
        - include only datasets defined in DATASETS_LIST (if settings.DATASETS_LIST is defined)
        - exclude any datasets in DATASETS_EXCLUDE list (if settings.DATASETS_EXCLUDE is defined)
        """
        queryset = queryset.filter(Q(version=None) | Q(is_default_version=True))

        if settings.DATASETS_LIST is not None:
            queryset = queryset.filter(name__in=settings.DATASETS_LIST)
        if settings.DATASETS_EXCLUDE is not None:
            queryset = queryset.exclude(name__in=settings.DATASETS_EXCLUDE)
        return queryset
