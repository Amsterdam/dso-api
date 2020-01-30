from rest_framework.response import Response
from rest_framework.views import APIView

from dso_api.datasets.models import Dataset
from dso_api.lib.schematools.db import create_tables
from dso_api.lib.schematools.types import DatasetSchema


class SchemaUploadView(APIView):
    swagger_schema = None  # Hide from swagger

    def post(self, request):
        schema = DatasetSchema.from_dict(request.data)
        Dataset.objects.create(name=schema.id, schema_data=schema.json_data())
        create_tables(schema)
        return Response(f"Dataset {schema.id} created")
