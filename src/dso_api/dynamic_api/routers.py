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
the :func:`~schematools.contrib.django.factories.model_factory` and
:func:`~dso_api.dynamic_api.views.viewset_factory`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from itertools import chain
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.core import checks
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.urls import NoReverseMatch, URLPattern, path, reverse
from django.views.generic import RedirectView
from rest_framework import routers
from schematools.contrib.django.factories import remove_dynamic_models
from schematools.contrib.django.models import Dataset
from schematools.naming import to_snake_case

from .datasets import get_active_datasets
from .models import SealedDynamicModel
from .openapi import get_openapi_view
from .serializers import clear_serializer_factory_cache
from .utils import get_view_name
from .views import (
    APIIndexView,
    DatasetDocView,
    DatasetMVTSingleView,
    DatasetMVTView,
    DatasetTileJSONView,
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
        "In de DSO-API worden alle datasets van de Gemeente Amsterdam beschikbaar gesteld.\n"
        "Algemene uitleg vind je op [https://api.data.amsterdam.nl/v1/docs/](/v1/docs/)."
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
        if not ds.enable_db:
            return []
        try:
            api_url = reverse("dynamic_api:openapi", kwargs={"dataset_name": dataset_id})
            return [
                {
                    "name": "production",
                    "api_url": base + api_url,
                    "specification_url": base + api_url,
                    "documentation_url": f"{base}/v1/docs/datasets/{ds.path}.html",
                }
            ]
        except NoReverseMatch as e:
            logger.warning("dataset %s: %s", dataset_id, e)
            return []

    def get_related_apis(self, ds: Dataset, base: str):
        if ds.enable_db and ds.has_geometry_fields:
            # WFS and MVT is only created for datasets
            # that are directly backed by a local database.
            ds_id = ds.schema.id
            wfs_url = reverse("dynamic_api:wfs", kwargs={"dataset_name": ds_id})
            mvt_url = reverse("dynamic_api:mvt", kwargs={"dataset_name": ds_id})
            return [
                {"type": "WFS", "url": base + wfs_url},
                {"type": "MVT", "url": base + mvt_url},
            ]
        else:
            return []


class DynamicRouter(routers.DefaultRouter):
    """Router that dynamically creates all views and viewsets based on the Dataset models."""

    def __init__(self):
        super().__init__(trailing_slash=False)
        self.include_format_suffixes = False
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
        the :func:`~schematools.contrib.django.factories.model_factory` and
        :func:`~dso_api.dynamic_api.views.viewset_factory`.
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
        api_datasets = [ds for ds in db_datasets if ds.enable_api]
        dataset_routes = self._build_db_viewsets(api_datasets)
        doc_urls = self._build_doc_views(api_datasets)

        # OpenAPI views
        openapi_urls = self._build_openapi_views(api_datasets)

        # Sub Index views for sub paths of datasets
        index_urls = self._build_index_views(api_datasets)

        # mvt and wfs views
        mvt_urls = self._build_mvt_views(api_datasets)
        wfs_urls = self._build_wfs_views(api_datasets)

        # Atomically copy the new viewset registrations
        self.registry = self.static_routes + dataset_routes
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
            dataset.schema  # noqa: B018 (load data early)

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
        from rest_framework.routers import Route

        # Define custom routes that support both slash and no-slash
        self.routes = [
            # List route
            Route(
                url=r"^{prefix}$",
                mapping={"get": "list"},
                name="{basename}-list",
                detail=False,
                initkwargs={"suffix": "List"},
            ),
            # List route with trailing slash
            Route(
                url=r"^{prefix}/$",
                mapping={"get": "list"},
                name="{basename}-list-slash",
                detail=False,
                initkwargs={"suffix": "List"},
            ),
            # Detail route
            Route(
                url=r"^{prefix}/(?P<pk>[^/]+)$",
                mapping={"get": "retrieve"},
                name="{basename}-detail",
                detail=True,
                initkwargs={"suffix": "Instance"},
            ),
            # Detail route with trailing slash
            Route(
                url=r"^{prefix}/(?P<pk>[^/]+)/?$",
                mapping={"get": "retrieve"},
                name="{basename}-detail-slash",
                detail=True,
                initkwargs={"suffix": "Instance"},
            ),
        ]

        tmp_router = routers.DefaultRouter()
        tmp_router.routes = self.routes

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
                tmp_router.register(url_prefix, viewset, basename=f"{dataset_id}-{table_id}")

        return tmp_router.registry

    def _build_doc_views(self, datasets: Iterable[Dataset]) -> Iterator[URLPattern]:
        for dataset in datasets:
            dataset_id = dataset.schema.id  # not dataset.name which is mangled.
            yield path(
                f"/docs/datasets/{dataset.path}.html",
                DatasetDocView.as_view(),
                name="docs-dataset",
                kwargs={"dataset_name": dataset_id},
            )

            if not dataset.has_geometry_fields:
                continue

            # The old WFS-documentation pages (``/v1/docs/wfs-datasets/...``) have been merged with
            # the index page that django-gisserver already provides.
            # It has a more accurate overview, as that documentation is generated
            # from the FeatureType definition, and not re-generated from Amsterdam Schema.
            yield path(
                f"/docs/wfs-datasets/{dataset.path}.html",
                RedirectView.as_view(pattern_name="wfs"),
                kwargs={"dataset_name": dataset.id},
            )

    def _build_openapi_views(self, datasets: Iterable[Dataset]) -> list[URLPattern]:
        """Build the OpenAPI viewsets per dataset"""
        results = []
        for dataset in datasets:
            dataset_id = dataset.schema.id
            results.append(
                path(
                    f"/{dataset.path}",
                    get_openapi_view(dataset),
                    name="openapi",
                    kwargs={"dataset_name": dataset_id},
                )
            )
            results.append(
                path(
                    f"/{dataset.path}/",
                    get_openapi_view(dataset),
                    name="openapi-slash",
                    kwargs={"dataset_name": dataset_id},
                )
            )
            results.append(
                path(
                    f"/{dataset.path}/openapi.yaml",
                    get_openapi_view(dataset, response_format="yaml"),
                    name="openapi-yaml",
                    kwargs={"dataset_name": dataset_id},
                )
            )
            results.append(
                path(
                    f"/{dataset.path}/openapi.json",
                    get_openapi_view(dataset, response_format="json"),
                    name="openapi-json",
                    kwargs={"dataset_name": dataset_id},
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
                    f"/mvt/{dataset.path}/",
                    DatasetMVTSingleView.as_view(),
                    name="mvt-slash",
                    kwargs={"dataset_name": dataset_id},
                )
            ),
            results.append(
                path(
                    f"/mvt/{dataset.path}",
                    DatasetMVTSingleView.as_view(),
                    name="mvt",
                    kwargs={"dataset_name": dataset_id},
                )
            )
            results.append(
                path(
                    f"/mvt/{dataset.path}/tilejson.json",
                    DatasetTileJSONView.as_view(),
                    name="mvt-tilejson",
                    kwargs={"dataset_name": dataset_id},
                )
            ),
            results.append(
                path(
                    f"/mvt/{dataset.path}/<table_name>/",
                    DatasetTileJSONView.as_view(),
                    name="mvt-tilejson-table-slash",
                    kwargs={"dataset_name": dataset_id},
                )
            ),
            results.append(
                path(
                    f"/mvt/{dataset.path}/<table_name>",
                    DatasetTileJSONView.as_view(),
                    name="mvt-tilejson-table",
                    kwargs={"dataset_name": dataset_id},
                )
            ),
            results.append(
                path(
                    f"/mvt/{dataset.path}/<table_name>/<int:z>/<int:x>/<int:y>.pbf",
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
                    f"/wfs/{dataset.path}/",
                    DatasetWFSView.as_view(),
                    name="wfs-slash",
                    kwargs={"dataset_name": dataset_id},
                )
            ),
            results.append(
                path(
                    f"/wfs/{dataset.path}",
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
                    f"/{p}/",
                    DynamicAPIIndexView.as_view(path=p, name=name),
                    name=f"{p}-index-slash",
                )
            )
            results.append(
                path(
                    f"/{p}",
                    DynamicAPIIndexView.as_view(path=p, name=name),
                    name=f"{p}-index",
                )
            )
        return results

    def _make_url(self, prefix, url_path):
        """Generate the URL for the viewset"""
        if prefix:
            url_path = f"/{prefix}/{url_path}"
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
        if field.remote_field is not None and isinstance(field.remote_field.model, str):
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
