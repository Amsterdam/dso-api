from django.shortcuts import render
from drf_spectacular.utils import extend_schema
from drf_spectacular.views import SpectacularSwaggerView


class DSOSwaggerView(SpectacularSwaggerView):
    template_name_js = "dso_api/dynamic_api/swagger_ui.js"

    @extend_schema(exclude=True)
    def get(self, request, dataset_name, *args, **kwargs):
        self.url = f"/v1/{dataset_name}"
        return super().get(request, *args, **kwargs)


def oauth2_redirect(request):
    return render(request, template_name="dso_api/dynamic_api/oauth2_redirect.html")
