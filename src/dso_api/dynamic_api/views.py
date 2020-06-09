from collections import UserList
from typing import List, Type

from django.contrib.gis.db.models import GeometryField
from django.db import models
from django.http import Http404, JsonResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from gisserver.exceptions import WFSException, InvalidParameterValue
from gisserver.features import FeatureType, ServiceDescription
from gisserver.views import WFSView
from schematools.contrib.django.models import DynamicModel

from rest_framework import viewsets, status
from rest_framework_dso import crs, fields
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.views import DSOViewMixin
from dso_api.dynamic_api import permissions

from . import filterset, locking, serializers
from .permissions import get_unauthorized_fields


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

        identifier = self.request.dataset.temporal("identifier", None)

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
    serializer_class = serializers.serializer_factory(model)
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


class DatasetWFSView(WFSView):
    """A WFS view for a single dataset.

    This view does not need a factory-logic as we don't need named-integration
    in the URLConf. Instead, we can resolve the 'dataset' via the URL kwargs.
    """

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

    def get_service_description(self, service: str) -> ServiceDescription:
        dataset_name = self.kwargs["dataset_name"]
        return ServiceDescription(
            title=dataset_name.title(),
            keywords=["wfs", "amsterdam", "datapunt"],
            provider_name="Gemeente Amsterdam",
            provider_site="https://data.amsterdam.nl/",
            contact_person="Onderzoek, Informatie en Statistiek",
        )

    def get_feature_types(self) -> List[FeatureType]:
        """Generate map feature layers for all models that have geometry data."""
        typenames = self.KVP.get("TYPENAMES")
        models1 = (
            {
                name: model
                for name, model in self.models.items()
                if name in typenames.split(",")
            }
            if typenames
            else self.models
        )
        if not models1:
            raise InvalidParameterValue(
                "typename",
                f"Typename '{typenames}' doesn't exist in this server. "
                f"Please check the capabilities and reformulate your request.",
            ) from None

        if self.KVP["REQUEST"].upper() != "GETCAPABILITIES":
            self.check_permissions(self.request, models1.values())
        return [
            # TODO: Extend FeatureType with extra meta data
            # the get_unauthorized_fields() part of get_field_names() is an
            # expensive operation, hence this is only read when needed.
            FeatureType(
                model,
                fields=LazyList(self.get_field_names, model),
                crs=crs.DEFAULT_CRS,
                other_crs=crs.OTHER_CRS,
            )
            for model in models1.values()
            if self._has_geometry_field(model)
        ]

    def get_field_names(self, model):
        """Define which fields should be exposed with the model.

        Instead of opting for the "__all__" value of django-gisserver,
        provide an exist list of fields so unauthorized fields are excluded.
        """
        unauthorized_fields = get_unauthorized_fields(self.request, model)
        fields = []
        for model_field in model._meta.get_fields():
            if model_field.name in unauthorized_fields:
                continue

            if isinstance(model_field, models.ForeignKey):
                # Don't let it query on the relation value yet
                field_name = model_field.attname
            else:
                field_name = model_field.name

            fields.append(field_name)
        return fields

    def _has_geometry_field(self, model):
        return any(isinstance(f, GeometryField) for f in model._meta.get_fields())

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


class LazyList(UserList):
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    @cached_property
    def data(self):
        return self.func(*self.args, **self.kwargs)
