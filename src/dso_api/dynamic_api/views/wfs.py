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
from __future__ import annotations

import re
from collections import UserList
from typing import List, Union

from django.conf import settings
from django.contrib.gis.db.models import GeometryField
from django.db import models
from django.http import Http404
from django.urls import reverse
from django.utils.functional import cached_property
from gisserver.exceptions import InvalidParameterValue, PermissionDenied
from gisserver.features import ComplexFeatureField, FeatureField, FeatureType, ServiceDescription
from gisserver.views import WFSView
from schematools.contrib.django.models import Dataset
from schematools.utils import toCamelCase

from dso_api.dynamic_api import permissions
from dso_api.dynamic_api.views import APIIndexView
from rest_framework_dso import crs

FieldDef = Union[str, FeatureField]
RE_SIMPLE_NAME = re.compile(
    r"^(?P<ns>[a-z0-9_]+:)?(?P<name>[a-z0-9_]+)(?P<variant>-[a-z0-9_]+)?$", re.I
)


class AuthenticatedFeatureType(FeatureType):
    """Extended WFS feature type definition that also performs authentication."""

    def __init__(self, queryset, *, wfs_view: DatasetWFSView, **kwargs):
        super().__init__(queryset, **kwargs)
        self.wfs_view = wfs_view

    def check_permissions(self, request):
        """Perform the access check for a particular request.
        This retrieves the accessed models, and relays further processing in the view.
        """
        models = [self.model]

        # If the ?expand=.. parameter is used, check the type definition for
        # any expanded elements. These models are also checked for permission.
        for xsd_element in self.xsd_type.complex_elements:
            related_model = xsd_element.type.source
            if related_model is not None:
                models.append(related_model)

        self.wfs_view.check_permissions(request, models)


class DatasetWFSIndexView(APIIndexView):
    """An overview of the available WFS endpoints.
    This makes sure a request to ``/wfs/`` renders a reasonable index page.
    """

    name = "DSO-API WFS Endpoints"  # for browsable API.
    description = "To use the DSO-API, see the documentation at \
        <https://api.data.amsterdam.nl/v1/docs/>. \
        For information on using WFS see WFS documentation at \
        <https://api.data.amsterdam.nl/v1/docs/generic/wfs.html>"
    api_type = "WFS"
    datasets = [
        ds for ds in Dataset.objects.db_enabled().order_by("name") if ds.has_geometry_fields
    ]

    def get_environments(self, ds: Dataset, base: str):
        return [
            {
                "name": "production",
                "api_url": base + reverse("dynamic_api:wfs", kwargs={"dataset_name": ds.name}),
                "specification_url": base
                + reverse("dynamic_api:swagger-ui", kwargs={"dataset_name": ds.name}),
                "documentation_url": f"{base}/v1/docs/wfs-datasets/{ds.schema.id}.html",
            }
        ]

    def get_related_apis(self, ds: Dataset, base: str):
        related_apis = []
        if ds.has_geometry_fields:
            related_apis = [
                {
                    "type": "rest_json",
                    "url": base + reverse(f"dynamic_api:openapi-{ds.schema.id}"),
                },
                {
                    "type": "MVT",
                    "url": base
                    + reverse("dynamic_api:mvt-single-dataset", kwargs={"dataset_name": ds.name}),
                },
            ]
        return related_apis


class DatasetWFSView(WFSView):
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

    index_template_name = "dso_api/dynamic_api/wfs_dataset.html"

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    def setup(self, request, *args, **kwargs):
        """Initial setup logic before request handling:

        Resolve the current model or return a 404 instead.
        """
        super().setup(request, *args, **kwargs)
        from ..urls import router

        dataset_name = self.kwargs["dataset_name"]
        try:
            self.models = router.all_models[dataset_name]
        except KeyError:
            raise Http404("Invalid dataset") from None

        # Allow to define the expand or embed fields on request.
        expand = request.GET.get("expand", "")
        self.expand_fields = set(expand.split(",")) if expand else set()

        embed = request.GET.get("embed", "")
        self.embed_fields = set(embed.split(",")) if embed else set()

    def get_index_context_data(self, **kwargs):
        """Context data for the HTML root page"""
        expandable_fields = set()
        for model in self.models.values():
            expandable_fields.update(
                field.name
                for field in model._meta.get_fields()
                if isinstance(field, models.ForeignKey)
            )

        context = super().get_index_context_data(**kwargs)

        context["expandable_fields"] = sorted(expandable_fields)
        return context

    def get_service_description(self, service: str) -> ServiceDescription:
        dataset_name = self.kwargs["dataset_name"]
        schema = Dataset.objects.get(name=dataset_name).schema

        return ServiceDescription(
            title=schema.title or dataset_name.title(),
            abstract=schema.description,
            keywords=["wfs", "amsterdam", "datapunt"],
            provider_name="Gemeente Amsterdam",
            provider_site="https://data.amsterdam.nl/",
            contact_person="Onderzoek, Informatie en Statistiek",
        )

    def get_feature_types(self) -> List[FeatureType]:
        """Generate map feature layers for all models that have geometry data."""
        typenames = self.KVP.get("TYPENAMES")
        if not typenames:
            # Need to parse all models (e.g. GetCapabilities)
            subset = self.models
        else:
            # Already filter the number of exported features, to avoid intense database queries.
            # The dash is used as variants of the same feature. The xmlns: prefix is also removed
            # since it can differ depending on the NAMESPACES parameter.
            requested_names = set(
                RE_SIMPLE_NAME.sub(r"\g<name>", name) for name in typenames.split(",")
            )
            subset = {
                name: model for name, model in self.models.items() if name in requested_names
            }

            if not subset:
                raise InvalidParameterValue(
                    "typename",
                    f"Typename '{typenames}' doesn't exist in this server. "
                    f"Please check the capabilities and reformulate your request.",
                ) from None

        features = []
        for model in subset.values():
            geo_fields = self._get_geometry_fields(model)
            base_name = model._meta.model_name
            base_title = model._meta.verbose_name

            # When there are multiple geometry fields for a model,
            # multiple features are generated so both can be displayed.
            # By default, QGis and friends only show the first geometry.
            for i, geo_field in enumerate(geo_fields):
                # the get_unauthorized_fields() part of get_feature_fields() is an
                # expensive operation, hence this is only read when needed.
                fields = LazyList(self.get_feature_fields, model, geo_field.name)

                if i == 0:
                    name = base_name
                    title = base_title
                else:
                    name = f"{base_name}-{geo_field.name}"
                    title = f"{base_title} ({geo_field.verbose_name})"

                feature = AuthenticatedFeatureType(
                    model,
                    name=name,
                    title=title,
                    fields=fields,
                    display_field_name=model.get_display_field(),
                    geometry_field_name=geo_field.name,
                    crs=crs.DEFAULT_CRS,
                    other_crs=crs.OTHER_CRS,
                    wfs_view=self,
                    show_name_field=model.has_display_field(),
                )
                features.append(feature)
        return features

    def get_feature_fields(self, model, main_geometry_field_name) -> List[FieldDef]:
        """Define which fields should be exposed with the model.

        Instead of opting for the "__all__" value of django-gisserver,
        provide an explicit list of fields so unauthorized fields are excluded.
        """
        unauthorized_fields = permissions.get_unauthorized_fields(self.request, model)
        fields = []
        other_geo_fields = []
        for model_field in model._meta.get_fields():
            if toCamelCase(model_field.name) in unauthorized_fields:
                continue

            if isinstance(model_field, models.ForeignKey):
                # Don't let it query on the relation value yet
                field_name = model_field.attname

                if model_field.name in self.expand_fields:
                    # Include an expanded field definition to the list of fields
                    fields.append(
                        ComplexFeatureField(
                            model_field.name,
                            fields=self.get_expanded_fields(model_field.related_model),
                        )
                    )
                if model_field.name in self.embed_fields:
                    # The "Model.id" field is added
                    fields.extend(
                        self.get_embedded_fields(
                            model_field.name,
                            model_field.related_model,
                            pk_attr=field_name,
                        )
                    )
            elif model_field.is_relation:
                # don't support other relations yet
                # Note: this also needs updates in get_index_context_data()!
                continue
            else:
                field_name = model_field.name

            if isinstance(model_field, GeometryField) and field_name != main_geometry_field_name:
                # The other geometry fields are moved to the end, so the main geometryfield
                # is listed as first value in a feature. This makes sure QGis and friends
                # render that particular field.
                other_geo_fields.append(model_field.name)
            else:
                fields.append(field_name)

        return fields + other_geo_fields

    def get_expanded_fields(self, model) -> List[FieldDef]:
        """Define which fields to include in an expanded relation.
        This is a shorter list, as including a geometry has no use here.
        Relations are also avoided as these won't be expanded anyway.
        """
        unauthorized_fields = permissions.get_unauthorized_fields(self.request, model)
        return [
            model_field.name
            for model_field in model._meta.get_fields()  # type: models.Field
            if not model_field.is_relation
            and toCamelCase(model_field.name) not in unauthorized_fields
            and not isinstance(model_field, GeometryField)
        ]

    def get_embedded_fields(self, relation_name, model, pk_attr=None) -> List[FieldDef]:
        """Define which fields to embed as flattened fields."""
        unauthorized_fields = permissions.get_unauthorized_fields(self.request, model)
        return [
            FeatureField(
                name=f"{relation_name}.{model_field.name}",  # can differ if needed
                model_attribute=(
                    f"{relation_name}.{model_field.name}"
                    if not model_field.primary_key or not pk_attr
                    else pk_attr  # optimization, redirect queries to the parent model
                ),
            )
            for model_field in model._meta.get_fields()  # type: models.Field
            if not model_field.is_relation
            and toCamelCase(model_field.name) not in unauthorized_fields
            and not isinstance(model_field, GeometryField)
        ]

    def _get_geometry_fields(self, model) -> List[GeometryField]:
        return [f for f in model._meta.get_fields() if isinstance(f, GeometryField)]

    def check_permissions(self, request, models):
        """
        Check if the request should be permitted.
        """
        for permission in self.get_permissions():
            if not permission.has_permission(request, self, models):
                self.permission_denied(request, message=getattr(permission, "message", None))

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

    def permission_denied(self, request, message=None):
        """
        If request is not permitted, determine what kind of exception to raise.
        """
        # if request.authenticators and not request.successful_authenticator:
        #     raise exceptions.NotAuthenticated()
        raise PermissionDenied("check_permissions")


class LazyList(UserList):
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @cached_property
    def data(self):
        return self.func(*self.args, **self.kwargs)
