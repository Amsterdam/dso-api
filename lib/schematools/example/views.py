import os

from rest_framework import serializers, viewsets
from schematools.db import schema_models_factory
from schematools.schema.utils import schema_defs_from_url

SCHEMA_URL = os.getenv("SCHEMA_URL")


def fetch_viewsets():
    result = {}
    for schema_name, dataset in schema_defs_from_url(SCHEMA_URL).items():
        for model_cls in schema_models_factory(dataset):

            meta_serializer_cls = type(
                "Meta", (object,), {"model": model_cls, "fields": "__all__"}
            )
            serializer_class = type(
                f"{model_cls.__name__}Serializer",
                (serializers.ModelSerializer,),
                {"Meta": meta_serializer_cls},
            )
            viewset_attrs = {
                "queryset": model_cls.objects.all(),
                "serializer_class": serializer_class,
            }

        result[schema_name] = type(
            f"{schema_name.capitalize()}ViewSet",
            (viewsets.ModelViewSet,),
            viewset_attrs,
        )

    return result

