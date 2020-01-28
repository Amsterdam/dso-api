from rest_framework.views import APIView
from rest_framework.response import Response

from schematools.schema.types import DatasetSchema
from schematools.db import create_tables

from dso_api.datasets.models import Dataset


class SchemaUploadView(APIView):
    def post(self, request):
        schema = DatasetSchema.from_dict(request.data)
        Dataset.objects.create(name=schema.id, schema_data=schema.json_data())
        create_tables(schema)
        return Response(f"Dataset {schema.id} created")
