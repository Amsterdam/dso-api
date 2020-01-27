from typing import Type

from django.http import JsonResponse
from rest_framework import viewsets
from schematools.models import DynamicModel

from rest_framework_dso.pagination import DSOPageNumberPagination
from . import serializers


def reload_patterns(request):
    """A view that reloads the current patterns."""
    from .urls import router

    new_models = router.reload()

    return JsonResponse({
        'models': [
            f"{model._dataset_id}/{model._table_id}" for model in new_models
        ]
    })


class DynamicApiViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for an API, that is """
    pagination_class = DSOPageNumberPagination

    #: Define the model class to use (e.g. in .as_view() call / subclass)
    model: Type[DynamicModel] = None

    def get_queryset(self):
        return self.model.objects.all()

    def get_serializer_class(self):
        """Dynamically generate the serializer class for this model."""
        return serializers.serializer_factory(self.model)


def viewset_factory(model: Type[DynamicModel]) -> Type[DynamicApiViewSet]:
    """Generate the viewset for a schema."""
    return type(
        f"{model.__class__.__name__}ViewSet", (DynamicApiViewSet,), {
            'model': model,
        }
    )
