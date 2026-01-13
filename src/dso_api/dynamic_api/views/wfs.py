"""The WFS views expose all geographic datasets as WFS endpoints and feature types.

The main logic of the WFS server can be found in the `django-gisserver`_
package. By overriding it's :class:`~gisserver.views.WFSView` class,
our dynamic models can be introduced into the `django-gisserver`_ logic.
Specifically, the following happens:

* The ``FeatureType`` class is overwritten to implement permission checks.
* The ``WFSView.get_feature_types()`` dynamically returns the feature types
  based on the datasets.
* The query parameters ``?expand`` and ``?embed`` extend the server logic
  to provide object-embedding at the feature type level.

The WFS server itself doesn't have any awareness of Amsterdam Schema, or the
fact that model definitions are dynamically generated. It's output and filter
logic is purely based on the provided ``FeatureType`` definition. Hence, the
server can act differently based on authorization logic - as we provide a
different ``FeatureType`` definition in such case.

By making the dataset name part of the view ``kwargs``,
each individual dataset becomes a separate WFS server endpoint.
The models of that dataset become WFS feature types.

.. _django-gisserver: https://github.com/Amsterdam/django-gisserver
"""

import logging
import re
from collections import UserList

from django.conf import settings
from django.contrib.gis.db.models import GeometryField
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.http import Http404
from django.urls import reverse
from django.utils import translation
from django.utils.functional import cached_property
from gisserver.exceptions import InvalidParameterValue, PermissionDenied
from gisserver.features import ComplexFeatureField, FeatureField, FeatureType, ServiceDescription
from gisserver.geometries import CRS
from gisserver.parsers import wfs20
from gisserver.views import WFSView
from schematools.contrib.django.models import DynamicModel
from schematools.naming import toCamelCase
from schematools.types import DatasetTableSchema, RowLevelAuthorisation

from dso_api.dynamic_api.constants import DEFAULT
from dso_api.dynamic_api.datasets import get_active_datasets
from dso_api.dynamic_api.permissions import CheckModelPermissionsMixin
from dso_api.dynamic_api.temporal import filter_temporal_slice
from rest_framework_dso import crs

from .index import APIIndexView

logger = logging.getLogger(__name__)
RE_SIMPLE_NAME = re.compile(
    # Strip XML prefix and our custom -variant name.
    r"^(?P<ns>\{[^}]+})?(?P<name>[a-z0-9_]+)(?P<variant>-[a-z0-9_]+)?$",
    re.I,
)


class AuthenticatedFeatureType(FeatureType):
    """Extended WFS feature type definition that also performs authentication.
    This class tells django-gisserver how to render a model as WFS Feature.
    """

    def __init__(self, queryset, *, wfs_view: DatasetWFSView, **kwargs):
        super().__init__(queryset, **kwargs)
        self.wfs_view = wfs_view

    def check_permissions(self, request):
        """Perform the access check for a particular request.
        This retrieves the accessed models, and relays further processing in the view.
        """
        # If the main geometry is hidden behind an access scope,
        # accessing the WFS feature is moot (and risks exposure through direct model access)
        try:
            self.main_geometry_element  # noqa: B018
        except ImproperlyConfigured as err:
            raise PermissionDenied(
                "You do not have permission to perform this action, "
                "because you don't have permission to access the geometry element.",
                locator="typeNames",
            ) from err

    def get_queryset(self) -> models.QuerySet:
        # Only return active objects for now.
        # (no temporal filtering using WFS with <Before>, <After> filters, etc..)
        queryset = super().get_queryset()
        return filter_temporal_slice(self.wfs_view.request, queryset)

    def filter_related_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        # Apply temporal filtering on retrieved relations.
        return filter_temporal_slice(self.wfs_view.request, queryset)


class DatasetWFSIndexView(APIIndexView):
    """An overview of the available WFS endpoints.
    This makes sure a request to ``/wfs/`` renders a reasonable index page.
    """

    name = "WFS Endpoints"  # for browsable API.
    description = (
        "Alle WFS endpoints voor de gegevens in de DSO-API.\n\n"
        "Voor het gebruik van WFS endpoints, zie: "
        "[Datasets laden in GIS-pakketten](/v1/docs/generic/gis.html),"
        " en de algemene [documentatie van de DSO-API](/v1/docs/)."
    )
    api_type = "WFS"

    def get_datasets(self):
        return [
            ds
            for ds in get_active_datasets().db_enabled().order_by("name")
            if ds.has_geometry_fields
        ]

    def _build_version_endpoints(
        self,
        base: str,
        dataset_id: str,
        version: str,
        status: str,
        header: str | None = None,
        suffix: str = "",
    ):
        kwargs = {"dataset_name": dataset_id, "dataset_version": version}
        mvt_url = reverse(f"dynamic_api:mvt{suffix}", kwargs=kwargs)
        wfs_url = reverse(f"dynamic_api:wfs{suffix}", kwargs=kwargs)
        api_url = reverse(f"dynamic_api:openapi{suffix}", kwargs=kwargs)
        return {
            "header": header or f"Versie {version}",
            "status": status,
            "wfs_url": base + wfs_url,
            "doc_url": base + wfs_url,
            "api_url": base + api_url,
            "mvt_url": base + mvt_url,
        }


class DatasetWFSView(CheckModelPermissionsMixin, WFSView):
    """A WFS view for a single dataset.

    This extends the logic of django-gisserver to expose the dynamically generated
    as WFS :class:`~gisserver.features.FeatureType` objects. When the
    ``?extend=..``/``?expand=..`` parameters are given, a different set of feature types
    is generated so the WFS response contains complex nested objects.

    Permission checks happen in 2 levels. First, only the accessible fields are exposed
    in the feature types. Second, the :class:`AuthenticatedFeatureType` class extends
    the feature type logic to add permission-checking for table-level access.

    This view is not constructed with factory-logic as we don't need named-integration
    in the URLConf. Instead, we can resolve the 'dataset' via the URL kwargs.
    """

    xml_namespace = f"{settings.DATAPUNT_API_URL}v1/wfs/"

    def setup(self, request, *args, **kwargs):
        """Initial setup logic before request handling:

        Resolve the current model or return a 404 instead.
        """
        super().setup(request, *args, **kwargs)
        from dso_api.dynamic_api.urls import router

        dataset_name = self.kwargs["dataset_name"]
        dataset_version = self.kwargs["dataset_version"]
        try:
            self.models = router.all_models[dataset_name][dataset_version]
        except KeyError:
            raise Http404(f"Invalid dataset: {dataset_name}") from None

        # Get Amsterdam Schema for our generated model
        self.schema = next(iter(self.models.values())).table_schema().dataset

        # Allow to define the expand or embed fields on request.
        expand = request.GET.get("expand", "")
        self.expand_fields = set(expand.split(",")) if expand else set()

        embed = request.GET.get("embed", "")
        self.embed_fields = set(embed.split(",")) if embed else set()

    def check_permissions(self, feature_type: AuthenticatedFeatureType):
        """Implement permission check for accessing a feature."""
        # See which models the feature will touch
        accessed_models = [feature_type.model]

        # If the ?expand=.. parameter is used, check the type definition for
        # any expanded elements. These models are also checked for permission.
        for xsd_element in feature_type.xsd_type.all_complex_elements:
            related_model = xsd_element.type.source
            if related_model is not None:
                accessed_models.append(related_model)

        self.check_model_permissions(accessed_models)

    def render_index(self, service: str | None = None):
        """End-user docs are in Dutch, make sure any template translations work."""
        with translation.override("nl"):
            return super().render_index(service)

    def get_index_context_data(self, **kwargs):
        """Context data for the HTML root page"""
        embeddable_fields = self._get_embeddable_fields()
        dataset_version = self.kwargs["dataset_version"]
        suffix = "" if dataset_version == DEFAULT else "-version"
        return {
            **super().get_index_context_data(**kwargs),
            # Similar context as to DatasetMVTSingleView
            "schema": self.schema,
            "schema_auth": self.schema.auth,
            "dataset_has_auth": bool(self.schema.auth - {"OPENBAAR"}),
            "has_custom_schema": self.expand_fields or self.embed_fields,
            "embeddable_fields": embeddable_fields,
            "dataset_version": dataset_version,
            "mvt_url": reverse(f"dynamic_api:mvt{suffix}", kwargs=self.kwargs),
            "doc_url": reverse(f"dynamic_api:docs-dataset{suffix}", kwargs=self.kwargs),
        }

    def _get_embeddable_fields(self) -> list[dict]:
        """Describe the expandable fields (for the HTML documentation page)."""
        seen = set()
        expands = []
        for model in self.models.values():
            table_schema: DatasetTableSchema = model.table_schema()
            if table_schema.is_through_table or not table_schema.has_geometry_fields:
                continue

            for field in model._meta.get_fields():
                if field.name in seen or (table_schema.is_nested_table and field.name == "parent"):
                    continue

                if isinstance(field, models.ForeignKey):
                    seen.add(field.name)
                    field_schema = field.model.get_field_schema(field)
                    to_table = field_schema.related_table
                    wfs_doc = (
                        reverse("dynamic_api:wfs", kwargs={"dataset_name": to_table.dataset.id})
                        if to_table.dataset != table_schema.dataset
                        else ""
                    )

                    expands.append(
                        {
                            "name": field.name,
                            "description": to_table.description,
                            "relation_id": field_schema["relation"],
                            "target_doc": f"{wfs_doc}#feature-{to_table.id}",
                        }
                    )

        return expands

    def get_service_description(self, service: str | None = None) -> ServiceDescription:
        some_model: DynamicModel = next(iter(self.models.values()))
        schema = some_model.get_dataset_schema()

        try:
            publisher = self.schema.publisher.get("name")
        except NotImplementedError:
            # For tests that use DatabaseSchemaLoader without inlining publishers
            publisher = None

        return ServiceDescription(
            title=schema.title or self.kwargs["dataset_name"].title(),
            abstract=schema.description,
            keywords=["wfs", "amsterdam", "datapunt"],
            provider_name=self.schema.get("owner", "Gemeente Amsterdam"),
            provider_site="https://data.amsterdam.nl/",
            contact_person=publisher or "Cluster Digitalisering, Innovatie en Informatie (DII)",
        )

    def get_feature_types(self) -> list[FeatureType]:
        """Generate map feature layers for all models that have geometry data."""
        features = []
        # For performance, only the feature types are generated that are accessed by this request
        for model in self._get_requested_models():
            geo_fields = self._get_geometry_fields(model)
            if not geo_fields:
                continue

            base_name = model._meta.model_name
            base_title = model._meta.verbose_name
            table_schema = model.table_schema()

            # When there are multiple geometry fields for a model,
            # multiple features are generated so both can be displayed.
            # By default, QGis and friends only show the first geometry.
            for i, geo_field in enumerate(geo_fields):
                # the get_unauthorized_fields() part of get_feature_fields() is an
                # expensive operation, hence this is only read when needed.
                fields = LazyList(self.get_feature_fields, model, geo_field.name)

                # Make default WFS projection identical to the field.
                field_crs = CRS.from_srid(geo_field.srid)
                other_crs = [c for c in crs.ALL_CRS if c.srid != field_crs.srid]

                if i == 0:
                    name = base_name
                    title = base_title
                else:
                    name = f"{base_name}-{geo_field.name}"
                    title = f"{base_title} ({geo_field.verbose_name})"
                feature = AuthenticatedFeatureType(
                    model.objects.all(),
                    name=name,
                    title=title,
                    abstract=table_schema.description,
                    fields=fields,
                    display_field_name=model.get_display_field(),
                    geometry_field_name=geo_field.name,
                    crs=field_crs,
                    other_crs=other_crs,
                    wfs_view=self,
                    show_name_field=model.has_display_field(),
                )
                features.append(feature)
        return features

    def get_feature_fields(self, model, main_geometry_field_name) -> list[FeatureField]:
        """Define which fields should be exposed with the model.

        Instead of opting for the "__all__" value of django-gisserver,
        provide an explicit list of fields so unauthorized fields are excluded.
        """
        fields = []
        other_geo_fields = []
        is_index_view = self.is_index_request()
        for model_field in model._meta.get_fields():  # type models.Field
            if not is_index_view and not self.request.user_scopes.has_field_access(
                model.get_field_schema(model_field)
            ):
                continue

            # When there is Row Level Auth, we omit the field.
            rla: RowLevelAuthorisation | None = model.table_schema().rla
            if rla is not None and toCamelCase(model_field.name) in rla.targets:
                continue

            if isinstance(model_field, models.ForeignKey):
                # Don't let it query on the relation value yet
                field_name = model_field.attname

                if model_field.name in self.expand_fields:
                    # Include an expanded field definition to the list of fields
                    fields.append(
                        ComplexFeatureField(
                            model_field.name,
                            fields=self._get_expanded_fields(model_field.related_model),
                            abstract=model_field.help_text,
                        )
                    )
                if model_field.name in self.embed_fields:
                    # The "Model.id" field is added
                    fields.extend(
                        self._get_embedded_fields(
                            model_field.name,
                            model_field.related_model,
                            pk_attr=field_name,
                        )
                    )
            elif model_field.is_relation:
                # don't support other relations yet
                # Note: this also needs updates in get_index_context_data()!
                if not model_field.hidden and "_rev_" not in model_field.name:
                    logger.debug("WFS ignores relational field %s", model_field.name)
                continue
            else:
                field_name = model_field.name

            if isinstance(model_field, GeometryField) and field_name != main_geometry_field_name:
                # The other geometry fields are moved to the end, so the main geometryfield
                # is listed as first value in a feature. This makes sure QGis and friends
                # render that particular field.
                other_geo_fields.append(
                    FeatureField(
                        model_field.name,
                        abstract=model_field.help_text,
                    )
                )
            else:
                fields.append(
                    FeatureField(
                        field_name,
                        abstract=model_field.help_text,
                    )
                )

        return fields + other_geo_fields

    def _get_requested_models(self) -> list[type[DynamicModel]]:
        """Tell which models are accessed by the request.
        This allows for a more efficient call of get_feature_types(),
        as it doesn't dynamically have to generate the features which aren't accessed.
        """
        typenames = []
        if isinstance(self.ows_request, wfs20.DescribeFeatureType):
            typenames = self.ows_request.typeNames  # can be empty
        elif isinstance(self.ows_request, (wfs20.GetPropertyValue, wfs20.DescribeFeatureType)):
            for query in self.ows_request.queries:
                typenames.extend(query.get_type_names())

        if not typenames:
            # Need to parse all models, this is a request such as GetCapabilities,
            # or DescribeFeatureType without providing typeNames.
            return self.models.values()
        else:
            # Already filter the number of exported features, to avoid the costs of building them.
            # The dash is used as variants of the same feature. The xml namespace is also removed.
            requested_names = {RE_SIMPLE_NAME.sub(r"\g<name>", name) for name in typenames}
            models = [model for name, model in self.models.items() if name in requested_names]

            if not models:
                raise InvalidParameterValue(
                    f"Typename '{requested_names}' doesn't exist in this server. "
                    f"Please check the capabilities and reformulate your request.",
                    locator="typeNames",
                ) from None
            return models

    def _get_expanded_fields(self, model) -> list[FeatureField]:
        """Define which fields to include in an expanded relation.
        This is a shorter list, as including a geometry has no use here.
        Relations are also avoided as these won't be expanded anyway.
        """
        user_scopes = self.request.user_scopes
        return [
            FeatureField(
                model_field.name,
                abstract=model_field.help_text,
            )
            for model_field in model._meta.get_fields()  # type: models.Field
            if not model_field.is_relation
            and not isinstance(model_field, GeometryField)
            and user_scopes.has_field_access(model.get_field_schema(model_field))
        ]

    def _get_embedded_fields(self, relation_name, model, pk_attr=None) -> list[FeatureField]:
        """Define which fields to embed as flattened fields."""
        user_scopes = self.request.user_scopes
        return [
            FeatureField(
                name=f"{relation_name}.{model_field.name}",  # can differ if needed
                model_attribute=(
                    f"{relation_name}.{model_field.name}"
                    if not model_field.primary_key or not pk_attr
                    else pk_attr  # optimization, redirect queries to the parent model
                ),
                abstract=model_field.help_text,
            )
            for model_field in model._meta.get_fields()  # type: models.Field
            if not model_field.is_relation
            and not isinstance(model_field, GeometryField)
            and user_scopes.has_field_access(model.get_field_schema(model_field))
        ]

    def _get_geometry_fields(self, model) -> list[GeometryField]:
        # Return the geometry field with the mainGeometry field as the first item
        table_schema: DatasetTableSchema = model.table_schema()
        geometry_fields = []
        for f in model._meta.get_fields():
            if isinstance(f, GeometryField):
                if f.name == table_schema.main_geometry_field.db_name:
                    geometry_fields.insert(0, f)
                else:
                    geometry_fields.append(f)
        return geometry_fields


class LazyList(UserList):
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @cached_property
    def data(self):
        return self.func(*self.args, **self.kwargs)
