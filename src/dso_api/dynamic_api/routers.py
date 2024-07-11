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
from itertools import chain
from typing import TYPE_CHECKING, Iterable, Iterator

from django.apps import apps
from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.urls import NoReverseMatch, URLPattern, path, reverse
from rest_framework import routers
from schematools.contrib.django.factories import remove_dynamic_models
from schematools.contrib.django.models import Dataset
from schematools.naming import to_snake_case

from .datasets import get_active_datasets
from .models import SealedDynamicModel
from .openapi import get_openapi_json_view
from .remote import remote_serializer_factory, remote_viewset_factory
from .serializers import clear_serializer_factory_cache
from .utils import get_view_name
from .views import (
    APIIndexView,
    DatasetDocView,
    DatasetMVTSingleView,
    DatasetMVTView,
    DatasetWFSDocView,
    DatasetWFSView,
    viewset_factory,
)

logger = logging.getLogger(__name__)
reload_counter = 0

if TYPE_CHECKING:
    from schematools.contrib.django.models import DynamicModel


class DynamicAPIIndexView(APIIndexView):
    """An overview of API endpoints."""

    name = "DSO-API Datasets"  # for browsable API.
    description = (
        "To use the DSO-API, see the documentation at <https://api.data.amsterdam.nl/v1/docs/>. "
    )
    api_type = "rest_json"
    path = None

    def get_datasets(self) -> Iterable[Dataset]:
        datasets = super().get_datasets()
        if self.path:
            datasets = [ds for ds in datasets if ds.path.startswith(self.path)]
        return datasets

    def get_environments(self, ds: Dataset, base: str):
        dataset_id = ds.schema.id
        if ds.enable_db:
            api_url = reverse(f"dynamic_api:openapi-{dataset_id}")
            return [
                {
                    "name": "production",
                    "api_url": base + api_url,
                    "specification_url": base + api_url,
                    "documentation_url": f"{base}/v1/docs/datasets/{ds.path}.html",
                }
            ]
        else:
            # Remote proxies have no index page yet.
            # NOTE: no views are generated when endpoint_url is also empty.
            return [
                {
                    "name": "production",
                    "api_url": "",  # f"/v1/{ds.path}{{table_id}}"
                    "specification_url": "",
                    "documentation_url": f"{base}/v1/docs/datasets/{ds.path}.html",
                }
            ]

    def get_related_apis(self, ds: Dataset, base: str):
        if ds.enable_db and ds.has_geometry_fields:
            # WFS and MVT is only created for datasets
            # that are directly backed by a local database.
            ds_id = ds.schema.id
            wfs_url = reverse("dynamic_api:wfs", kwargs={"dataset_name": ds_id})
            mvt_url = reverse("dynamic_api:mvt-single-dataset", kwargs={"dataset_name": ds_id})
            return [
                {"type": "WFS", "url": base + wfs_url},
                {"type": "MVT", "url": base + mvt_url},
            ]
        else:
            return []


class DynamicRouter(routers.DefaultRouter):
    """Router that dynamically creates all views and viewsets based on the Dataset models."""

    include_format_suffixes = False

    def __init__(self):
        super().__init__(trailing_slash=True)
        self.all_models: dict[str, dict[str, type[DynamicModel]]] = {}
        self.static_routes = []
        self._doc_urls = []
        self._openapi_urls = []
        self._index_urls = []
        self._mvt_urls = []
        self._wfs_urls = []

    def get_api_root_view(self, api_urls=None):
        """Show the OpenAPI specification as root view."""
        return DynamicAPIIndexView.as_view()

    def is_initialized(self) -> bool:
        """Tell whether the router initialization was used to create viewsets."""
        # Models could be created (with enable_api=false), or remote viewsets could be created.
        return bool(self.all_models) or len(self.registry) > len(self.static_routes)

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

        try:
            self._initialize_viewsets()
        except Exception:  # noqa: B902
            # Cleanup a half-initialized state that would mess up the application.
            # This happens in runserver's autoreload mode. The BaseReloader.run() code
            # silences all URLConf exceptions in a `try: import urlconf; catch Exception: pass`.
            # This could leave the Django models in an half-initialized state.
            remove_dynamic_models()
            raise

    def get_urls(self):
        """Add extra URLs beside the registered viewsets."""
        return list(
            chain(
                super().get_urls(),
                self._doc_urls,
                self._openapi_urls,
                self._index_urls,
                self._mvt_urls,
                self._wfs_urls,
            )
        )

    def register(self, prefix, viewset, basename=None):
        """Overwritten function to preserve any manually added routes on reloading."""
        super().register(prefix, viewset, basename=basename)
        self.static_routes.append(self.registry[-1])

    def _initialize_viewsets(self) -> list[type[DynamicModel]]:
        """Build all viewsets, serializers, models and URL routes."""
        # Generate new viewsets for dynamic models
        clear_serializer_factory_cache()

        # Create all models, including those with no API enabled.
        db_datasets = list(get_active_datasets(api_enabled=None).db_enabled())
        generated_models = self._build_db_models(db_datasets)

        if settings.DEBUG and self._has_model_errors():
            # Don't continue initialization when the models are incorrectly constructed.
            # There is no need to raise an error here, as the router initialization happens while
            # the URLConf checks runs. Hence, by stopping initialization the actual system
            # check framework can continue its checks, and can pick up the actual model issues.
            logger.error(
                "System check revealed errors with generated models, "
                "will not initialize serializers and viewsets."
            )
            return []

        # Create viewsets only for datasets that have an API enabled
        db_datasets = [ds for ds in db_datasets if ds.enable_api]
        dataset_routes = self._build_db_viewsets(db_datasets)

        # Same for remote API's
        api_datasets = list(get_active_datasets().endpoint_enabled())
        remote_routes = self._build_remote_viewsets(api_datasets)

        datasets = db_datasets + api_datasets

        doc_urls = self._build_doc_views(datasets)

        # OpenAPI views
        openapi_urls = self._build_openapi_views(datasets)

        # Sub Index views for sub paths of datasets
        index_urls = self._build_index_views(datasets)

        # mvt and wfs views
        mvt_urls = self._build_mvt_views(datasets)
        wfs_urls = self._build_wfs_views(datasets)

        # Atomically copy the new viewset registrations
        self.registry = self.static_routes + dataset_routes + remote_routes
        self._doc_urls = doc_urls
        self._openapi_urls = openapi_urls
        self._index_urls = index_urls
        self._mvt_urls = mvt_urls
        self._wfs_urls = wfs_urls

        # invalidate the urls cache
        if hasattr(self, "_urls"):
            del self._urls

        return generated_models

    def _has_model_errors(self) -> bool:
        """Tell whether there are model errors"""
        return any(
            check.is_serious() and not check.is_silenced()
            for check in checks.run_checks(tags=["models"])
        )

    def _build_db_models(self, db_datasets: Iterable[Dataset]) -> list[type[DynamicModel]]:
        """Generate the Django models based on the dataset definitions."""
        generated_models = []

        # Because dataset are related, we need to 'prewarm'
        # the datasets cache (in schematools)
        for dataset in db_datasets:
            dataset.schema

        for dataset in db_datasets:  # type: Dataset
            dataset_id = dataset.schema.id  # not dataset.name which is mangled.
            new_models = {}

            models = dataset.create_models(
                base_app_name="dso_api.dynamic_api",
                base_model=SealedDynamicModel,
            )

            for model in models:
                logger.debug("Created model %s.%s", dataset_id, model.__name__)
                new_models[model._meta.model_name] = model

            self.all_models[dataset_id] = new_models

            generated_models.extend(new_models.values())

        # Perform system checks on the late generated models:
        return generated_models

    def _build_db_viewsets(self, db_datasets: Iterable[Dataset]):
        """Initialize viewsets that are linked to Django database models."""
        tmp_router = routers.SimpleRouter()
        db_datasets = {dataset.schema.id: dataset for dataset in db_datasets}

        # Generate views now that all models have been created.
        # This makes sure the 'to' field is resolved to an actual model class.
        for app_label, models_by_name in self.all_models.items():
            if app_label not in db_datasets:
                logger.debug("Skipping API creation for dataset: %s", app_label)
                continue

            for model in models_by_name.values():
                _validate_model(model)
                if model.has_parent_table():
                    # Do not create separate viewsets for nested tables.
                    continue

                dataset_id = to_snake_case(model.get_dataset_id())
                table_id = to_snake_case(model.get_table_id())

                # Determine the URL prefix for the model
                url_prefix = self._make_url(model.get_dataset_path(), table_id)

                logger.debug("Created viewset %s", url_prefix)
                viewset = viewset_factory(model)
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{dataset_id}-{table_id}",
                )

        return tmp_router.registry

    def _build_remote_viewsets(self, api_datasets: Iterable[Dataset]):
        """Initialize viewsets that are proxies for remote URLs"""
        tmp_router = routers.SimpleRouter()

        for dataset in api_datasets:
            dataset_id = dataset.schema.id

            for table in dataset.schema.tables:
                table_id = to_snake_case(table.id)

                # Determine the URL prefix for the model
                url_prefix = self._make_url(dataset.path, table_id)
                serializer_class = remote_serializer_factory(table)
                viewset = remote_viewset_factory(
                    endpoint_url=dataset.endpoint_url,
                    serializer_class=serializer_class,
                    table_schema=table,
                )
                tmp_router.register(
                    prefix=url_prefix,
                    viewset=viewset,
                    basename=f"{to_snake_case(dataset_id)}-{table.id}",
                )

        return tmp_router.registry

    def _build_doc_views(self, datasets: Iterable[Dataset]) -> Iterator[URLPattern]:
        for dataset in datasets:
            yield path(
                f"docs/datasets/{dataset.path}.html",
                DatasetDocView.as_view(),
                name=f"doc-{dataset.schema.id}",
                kwargs={"dataset_name": dataset.schema.id},
            )

            if not dataset.has_geometry_fields:
                continue

            yield path(
                f"docs/wfs-datasets/{dataset.path}.html",
                DatasetWFSDocView.as_view(),
                name=f"doc-wfs-{dataset.schema.id}",
                kwargs={"dataset_name": dataset.schema.id},
            )

    def _build_openapi_views(self, datasets: Iterable[Dataset]) -> list[URLPattern]:
        """Build the OpenAPI viewsets per dataset"""
        results = []
        for dataset in datasets:
            dataset_id = dataset.schema.id
            results.append(
                path(
                    dataset.path + "/",
                    get_openapi_json_view(dataset),
                    name=f"openapi-{dataset_id}",
                )
            )
        return results

    def _build_mvt_views(self, datasets: Iterable[Dataset]) -> list[URLPattern]:
        """Build the mvt views per dataset"""
        results = []
        for dataset in datasets:
            dataset_id = dataset.schema.id  # not dataset.name which is mangled.
            results.append(
                path(
                    "mvt/" + dataset.path + "/",
                    DatasetMVTSingleView.as_view(),
                    name="mvt-single-dataset",
                    kwargs={"dataset_name": dataset_id},
                )
            )
            results.append(
                path(
                    "mvt/" + dataset.path + "/<table_name>/<int:z>/<int:x>/<int:y>.pbf",
                    DatasetMVTView.as_view(),
                    name="mvt-pbf",
                    kwargs={"dataset_name": dataset_id},
                )
            )
        return results

    def _build_wfs_views(self, datasets: Iterable[Dataset]) -> list[URLPattern]:
        """Build the wfs views per dataset"""
        results = []
        for dataset in datasets:
            dataset_id = dataset.schema.id  # not dataset.name which is mangled.
            results.append(
                path(
                    "wfs/" + dataset.path + "/",
                    DatasetWFSView.as_view(),
                    name="wfs",
                    kwargs={"dataset_name": dataset_id},
                )
            )
        return results

    def _build_index_views(self, datasets: Iterable[Dataset]) -> list[URLPattern]:
        """Build index views for each sub path
        Datasets can be grouped on subpaths. This generates a view
        on each sub path with an index of datasets on that path.
        """

        # List unique sub paths in all datasets
        paths = []
        for ds in datasets:
            path_components = ds.path.split("/")
            ds_paths = [
                "/".join(path_components[0 : i + 1]) for i, x in enumerate(path_components)
            ]
            paths += ds_paths[0:-1]
        paths = set(paths)

        # Create an index view for each path
        results = []
        for p in paths:
            name = p.split("/")[-1].capitalize() + " Datasets"
            results.append(
                path(
                    p + "/",
                    DynamicAPIIndexView.as_view(path=p, name=name),
                    name=f"{p}-index",
                )
            )
        return results

    def _make_url(self, prefix, url_path):
        """Generate the URL for the viewset"""

        # Allow to add a prefix
        prefix = prefix.strip("/")  # extra strip for safety
        if prefix:
            url_path = f"{prefix}/{url_path}"

        return url_path

    def reload(self) -> dict[type[DynamicModel], str]:
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
            except NoReverseMatch:
                url = None  # API Disabled

            result[model] = url

        return result

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
        self._mvt_urls.clear()
        self._wfs_urls.clear()
        self._index_urls.clear()
        if hasattr(self, "_urls"):
            del self._urls

        # Clear models, serializers and app registries
        self.all_models.clear()
        remove_dynamic_models()


def _validate_model(model: type[DynamicModel]):
    """Validate whether the model's foreign keys point to actual resolved models.
    This is a check against incorrect definitions, which eases debugging in case it happens.
    Otherwise the error is likely something like "str has no attribute _meta" deep inside
    a third party library (django-filter) without having any context on what model fails.
    """
    for field in model._meta.get_fields():
        if field.remote_field is not None:
            if isinstance(field.remote_field.model, str):
                app_label = field.remote_field.model.split(".")[0]
                try:
                    dataset_app = apps.get_app_config(app_label)
                except LookupError as e:
                    if "No installed app with label" not in str(e):
                        raise
                    # Report the dataset we're working with.
                    raise LookupError(f"{e} (model = {model.get_dataset_schema()})") from e
                available = sorted(model._meta.model_name for model in dataset_app.get_models())
                raise ImproperlyConfigured(
                    f"Field {field} does not point to an existing model:"
                    f" {field.remote_field.model}. Loaded models are: {', '.join(available)}"
                )
