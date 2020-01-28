from dso_api.datasets.models import Dataset
from dso_api.datasets.types import DatasetSchema
from dso_api.dynamic_api.db import create_tables
from rest_framework.response import Response
from rest_framework.views import APIView


class SchemaUploadView(APIView):
    def post(self, request):
        schema = DatasetSchema.from_dict(request.data)
        Dataset.objects.create(name=schema.id, schema_data=schema.json_data())
        create_tables(schema)
        return Response(f"Dataset {schema.id} created")
