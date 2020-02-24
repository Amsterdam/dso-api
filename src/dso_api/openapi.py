from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator


class GeoEnabledSchemaGenerator(OpenAPISchemaGenerator):
    def get_operation(self, view, path, prefix, method, components, request):
        accept_crs_header = openapi.Parameter(
            "Accept-Crs",
            openapi.IN_HEADER,
            description="Accept-Crs header for Geo queries",
            required=False,
            type="string",
        )
        content_crs_header = openapi.Parameter(
            "Content-Crs",
            openapi.IN_HEADER,
            description="Content-Crs header for Geo queries",
            required=False,
            type="string",
        )
        operation = super().get_operation(
            view, path, prefix, method, components, request
        )
        operation.parameters.extend([accept_crs_header, content_crs_header])
        return operation
