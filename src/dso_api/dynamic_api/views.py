from __future__ import annotations

import re
from collections import UserList
from typing import List, Type, Union

from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos.geometry import GEOSGeometry
from django.db import models
from django.http import Http404, JsonResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from gisserver.exceptions import WFSException, InvalidParameterValue
from gisserver.features import (
    ComplexFeatureField,
    FeatureField,
    FeatureType,
    ServiceDescription,
)
from gisserver.views import WFSView
from schematools.contrib.django.models import Dataset, DynamicModel
from rest_pandas import PandasView, PandasCSVRenderer, PandasSerializer
from rest_framework import viewsets, status
from rest_framework import serializers as drf_serializers
from rest_framework_dso import crs, fields
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.views import DSOViewMixin
from dso_api.dynamic_api import permissions

from . import filterset, locking, serializers
from .permissions import get_unauthorized_fields

FieldDef = Union[str, FeatureField]
RE_SIMPLE_NAME = re.compile(
    r"^(?P<ns>[a-z0-9]+:)?(?P<name>[a-z0-9]+)(?P<variant>-[a-z0-9]+)?$", re.I
)


class PermissionDenied(WFSException):
    """Permission denied"""

    status_code = status.HTTP_403_FORBIDDEN
    reason = "permission denied"
    text_template = "You do not have permission to perform this action"


def reload_patterns(request):
    """A view that reloads the current patterns."""
    from .urls import router

    new_models = router.reload()

    return JsonResponse(
        {
            "models": [
                {
                    "schema": model._meta.app_label,
                    "table": model._meta.model_name,
                    "url": request.build_absolute_uri(url),
                }
                for model, url in new_models.items()
            ]
        }
    )


class TemporalRetrieveModelMixin:
    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.versioned:
            if self.request.dataset_temporal_slice is not None:
                temporal_value = self.request.dataset_temporal_slice["value"]
                start_field, end_field = self.request.dataset_temporal_slice["fields"]
                queryset = queryset.filter(
                    **{f"{start_field}__lte": temporal_value}
                ).filter(
                    models.Q(**{f"{end_field}__gte": temporal_value})
                    | models.Q(**{f"{end_field}__isnull": True})
                )
        return queryset

    def get_object(self, queryset=None):
        """
        Do some black magic, find things in DB's garbage bags.
        """
        if queryset is None:
            queryset = self.get_queryset()

        if not self.request.versioned:
            return super().get_object()

        pk = self.kwargs.get("pk")
        pk_field = self.request.dataset.identifier
        if pk_field != "pk":
            queryset = queryset.filter(
                models.Q(**{pk_field: pk}) | models.Q(pk=pk)
            )  # fallback to full id search.
        else:
            queryset = queryset.filter(pk=pk)

        identifier = self.request.dataset.temporal.get("identifier", None)

        # Filter queryset using GET parameters, if any.
        for field in queryset.model._table_schema.fields:
            if field.name != pk_field and field.name in self.request.GET:
                queryset = queryset.filter(**{field.name: self.request.GET[field.name]})

        if identifier is None:
            queryset = queryset.order_by(pk_field)
        else:
            queryset = queryset.order_by(identifier)

        obj = queryset.last()
        if obj is None:
            raise Http404(
                _("No %(verbose_name)s found matching the query")
                % {"verbose_name": queryset.model._meta.verbose_name}
            )
        return obj


class DynamicApiViewSet(
    TemporalRetrieveModelMixin,
    locking.ReadLockMixin,
    DSOViewMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Viewset for an API, that is DSO-compatible and dynamically generated.
    Each dynamically generated model in this server will receive a viewset.

    """

    pagination_class = DSOPageNumberPagination

    #: Make sure composed keys like (112740.024|487843.078) are allowed.
    #: The DefaultRouter won't allow '.' in URLs because it's used as format-type.
    lookup_value_regex = r"[^/]+"

    #: Define the model class to use (e.g. in .as_view() call / subclass)
    model: Type[DynamicModel] = None

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]


def _get_viewset_api_docs(
    serializer_class: Type[serializers.DynamicSerializer],
    filterset_class: Type[filterset.DynamicFilterSet],
    ordering_fields: list,
) -> str:
    """Generate the API documentation header for the viewset.
    This documentation is also shown in the Swagger / DRF HTML browser.
    """
    lines = []
    if filterset_class and filterset_class.base_filters:
        lines.append(
            "The following fields can be used as filter with `?FIELDNAME=...`:\n"
        )
        for name, filter_field in filterset_class.base_filters.items():
            description = filter_field.label  # other kwarg appear in .extra[".."]
            lines.append(f"* {name}=*{description}*")

    embedded_fields = getattr(serializer_class.Meta, "embedded_fields", [])
    if embedded_fields:
        if lines:
            lines.append("")
        lines.append("The following fields can be expanded with `?_expandScope=...`:\n")
        lines.extend(f"* {name}" for name in embedded_fields)
        lines.append("\nExpand everything using `_expand=true`.")

    lines.append("\nUse `?_fields=field,field2` to limit which fields to receive")

    if ordering_fields:
        lines.append("\nUse `?_sort=field,field2,-field3` to sort on fields")

    return "\n".join(lines)


def _get_ordering_fields(
    serializer_class: Type[serializers.DynamicSerializer],
) -> List[str]:
    """Make sure the ordering doesn't happen on foreign relations.
    This creates an unnecessary join, which can be avoided by sorting on the _id field.
    """
    return [
        name
        for name in serializer_class.Meta.fields
        if name not in {"_links", "schema"}
        and not isinstance(getattr(serializer_class, name, None), fields.EmbeddedField)
    ]


def viewset_factory(model: Type[DynamicModel]) -> Type[DynamicApiViewSet]:
    """Generate the viewset for a schema."""
    serializer_class = serializers.serializer_factory(model, 0)
    filterset_class = filterset.filterset_factory(model)
    ordering_fields = _get_ordering_fields(serializer_class)

    attrs = {
        "__doc__": _get_viewset_api_docs(
            serializer_class, filterset_class, ordering_fields
        ),
        "model": model,
        "queryset": model.objects.all(),  # also for OpenAPI schema parsing.
        "serializer_class": serializer_class,
        "filterset_class": filterset_class,
        "ordering_fields": ordering_fields,
    }
    return type(f"{model.__name__}ViewSet", (DynamicApiViewSet,), attrs)


class AuthenticatedFeatureType(FeatureType):
    """Extended WFS feature type definition that also performs authentication."""

    def __init__(self, queryset, *, wfs_view: DatasetWFSView, **kwargs):
        super().__init__(queryset, **kwargs)
        self.wfs_view = wfs_view

    def check_permissions(self, request):
        """Relay permission check to the view"""
        models = [self.model]

        # If the ?expand=.. parameter is used, check the type definition for
        # any expanded elements. These models are also checked for permission.
        for xsd_element in self.xsd_type.complex_elements:
            related_model = xsd_element.type.source
            if related_model is not None:
                models.append(related_model)

        self.wfs_view.check_permissions(request, models)


class DatasetWFSIndexView(TemplateView):
    """An overview of the WFS services"""

    template_name = "dso_api/dynamic_api/wfs_index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .urls import router

        dataset_names = set(router.all_models.keys())
        datasets = [
            (ds.name, ds.schema)
            for ds in Dataset.objects.db_enabled().order_by("name")
            if ds.name in dataset_names
        ]

        context["datasets"] = datasets
        return context


class DatasetWFSView(WFSView):
    """A WFS view for a single dataset.

    This view does not need a factory-logic as we don't need named-integration
    in the URLConf. Instead, we can resolve the 'dataset' via the URL kwargs.
    """

    index_template_name = "dso_api/dynamic_api/wfs_dataset.html"

    def setup(self, request, *args, **kwargs):
        """Initial setup logic before request handling:

        Resolve the current model or return a 404 instead.
        """
        super().setup(request, *args, **kwargs)
        from .urls import router

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
                name: model
                for name, model in self.models.items()
                if name in requested_names
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
        provide an exist list of fields so unauthorized fields are excluded.
        """
        unauthorized_fields = get_unauthorized_fields(self.request, model)
        fields = []
        other_geo_fields = []
        for model_field in model._meta.get_fields():
            if model_field.name in unauthorized_fields:
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

            if (
                isinstance(model_field, GeometryField)
                and field_name != main_geometry_field_name
            ):
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
        unauthorized_fields = get_unauthorized_fields(self.request, model)
        return [
            model_field.name
            for model_field in model._meta.get_fields()  # type: models.Field
            if not model_field.is_relation
            and model_field.name not in unauthorized_fields
            and not isinstance(model_field, GeometryField)
        ]

    def get_embedded_fields(self, relation_name, model, pk_attr=None) -> List[FieldDef]:
        """Define which fields to embed as flattened fields."""
        unauthorized_fields = get_unauthorized_fields(self.request, model)
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
            and model_field.name not in unauthorized_fields
            and not isinstance(model_field, GeometryField)
        ]

    def _get_geometry_fields(self, model) -> List[GeometryField]:
        return [f for f in model._meta.get_fields() if isinstance(f, GeometryField)]

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    def check_permissions(self, request, models):
        """
        Check if the request should be permitted.
        """
        for permission in self.get_permissions():
            if not permission.has_permission(request, self, models):
                self.permission_denied(
                    request, message=getattr(permission, "message", None)
                )

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


class DatasetCSVView(PandasView):
    def setup(self, request, *args, **kwargs):
        """Initial setup logic before request handling:

        Resolve the current model or return a 404 instead.
        """
        super().setup(request, *args, **kwargs)
        from .urls import router

        dataset_name = self.kwargs["dataset_name"]
        table_name = self.kwargs["table_name"]
        try:
            self.model = router.all_models[dataset_name][table_name]
        except KeyError:
            raise Http404("Invalid dataset") from None

    #: Custom permission that checks amsterdam schema auth settings
    permission_classes = [permissions.HasOAuth2Scopes]

    def get_queryset(self):
        return self.model.objects.all()

    def get_serializer_class(self):
        def _to_representation(self, instance):
            ret = super(self.__class__, self).to_representation(instance)
            for field_name in self.fields.keys():
                field_value = getattr(instance, field_name)
                if isinstance(field_value, GEOSGeometry):
                    ret[field_name] = field_value.wkt
            return ret

        # Dirty hack to make drf_spectacular happy :-(
        if not (hasattr(self, "model")):

            class Dummy(models.Model):
                pass

            self.model = Dummy

        return type(
            "CSVSerializer",
            (drf_serializers.ModelSerializer,),
            {
                "Meta": type(
                    "Meta",
                    (),
                    {
                        "fields": "__all__",
                        "model": self.model,
                        "list_serializer_class": PandasSerializer,
                    },
                ),
                "to_representation": _to_representation,
            },
        )

    renderer_classes = [PandasCSVRenderer]


class LazyList(UserList):
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @cached_property
    def data(self):
        return self.func(*self.args, **self.kwargs)
