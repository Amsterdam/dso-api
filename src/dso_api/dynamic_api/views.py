from typing import List, Type

from django.contrib.gis.db.models import GeometryField
from django.http import Http404, JsonResponse
from gisserver.types import CRS, WGS84

from dso_api.lib.schematools.models import DynamicModel
from gisserver.features import FeatureType, ServiceDescription
from gisserver.views import WFSView
from rest_framework import viewsets

from rest_framework_dso.pagination import DSOPageNumberPagination

from . import serializers
from .locking import ReadLockMixin

# Common projections for Dutch GIS systems:
RD_NEW = CRS.from_string("EPSG:28992")  # Amersfoort / RD New
WEB_MERCATOR = CRS.from_string("EPSG:3857")  # Spherical Mercator (Google Maps, ...)
ETRS89 = CRS.from_string("EPSG:4258")  # European Terrestrial Reference System 1989


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


class DynamicApiViewSet(ReadLockMixin, viewsets.ReadOnlyModelViewSet):
    """Viewset for an API, that is """

    pagination_class = DSOPageNumberPagination

    #: Make sure composed keys like (112740.024|487843.078) are allowed.
    #: The DefaultRouter won't allow '.' in URLs because it's used as format-type.
    lookup_value_regex = r"[^/]+"

    #: Define the model class to use (e.g. in .as_view() call / subclass)
    model: Type[DynamicModel] = None

    def get_queryset(self):
        return self.model.objects.all()

    def get_serializer_class(self):
        """Dynamically generate the serializer class for this model."""
        return serializers.serializer_factory(self.model)


def viewset_factory(model: Type[DynamicModel]) -> Type[DynamicApiViewSet]:
    """Generate the viewset for a schema."""
    embedded = sorted(f.name for f in model._meta.get_fields() if f.is_relation)
    attrs = {"model": model}
    if embedded:
        embedded_text = "\n • ".join(embedded)
        attrs["__doc__"] = f"The following fields can be expanded:\n • {embedded_text}"
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
            FeatureType(model, crs=RD_NEW, other_crs=[WGS84, WEB_MERCATOR, ETRS89])
            for name, model in self.models.items()
            if self._has_geometry_field(model)
        ]

    def _has_geometry_field(self, model):
        return any(isinstance(f, GeometryField) for f in model._meta.get_fields())
