from typing import List, Type

from django.contrib.gis.db.models import GeometryField
from django.db import models
from django.http import Http404, JsonResponse
from django.urls import reverse

from gisserver.features import FeatureType, ServiceDescription
from gisserver.views import WFSView
from rest_framework import viewsets, routers
from rest_framework_dso import crs, fields
from rest_framework_dso.pagination import DSOPageNumberPagination
from rest_framework_dso.views import DSOViewMixin
from dso_api.dynamic_api import permissions


from dso_api.lib.schematools.models import DynamicModel
from . import filterset, locking, serializers
from .permissions import get_unauthorized_fields


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


class DynamicAPIRootView(routers.APIRootView):
    """
    This is the generic [DSO-compatible](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/) API server.

    The following features are supported:

    * HAL-JSON based links, pagination and response structure.
    * Use `?expand=name1,name2` to sideload specific relations.
    * Use `?expand=true` to sideload all relations.

    The models in this server are generated from the Amsterdam Schema files.
    These are located at:
    [https://schemas.data.amsterdam.nl/datasets](https://schemas.data.amsterdam.nl/datasets)
    """  # noqa: E501

    #: Title shown in the root API view.
    name = "DSO-API"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response.content_type = "application/json"
        response.data["openapi"] = request.build_absolute_uri(reverse("openapi.json"))
        return response


class DynamicApiViewSet(
    locking.ReadLockMixin, DSOViewMixin, viewsets.ReadOnlyModelViewSet,
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
        lines.append("The following fields can be expanded with `?expand=...`:\n")
        lines.extend(f"* {name}" for name in embedded_fields)
        lines.append("\nExpand everything using `expand=true`.")

    if ordering_fields:
        lines.append("\nUse `?sort=field,field2,-field3` to sort on fields")

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
    filterset_class = filterset.filterset_factory(model)
    serializer_class = serializers.serializer_factory(model)
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
        return [
            # TODO: Extend FeatureType with extra meta data
            FeatureType(
                model,
                fields=self.get_field_names(model),
                crs=crs.DEFAULT_CRS,
                other_crs=crs.OTHER_CRS,
            )
            for name, model in self.models.items()
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
