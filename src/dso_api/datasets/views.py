from rest_framework.views import APIView
from rest_framework.response import Response


class SchemaUploadView(APIView):
    def post(self, request):
        breakpoint()
        return Response("ok")
