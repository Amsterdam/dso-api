from django.shortcuts import render
from drf_spectacular.views import SpectacularSwaggerView


class DSOSwaggerView(SpectacularSwaggerView):
    template_name_js = "dso_api/dynamic_api/swagger_ui.js"


def oauth2_redirect(request):
    return render(request, template_name="dso_api/dynamic_api/oauth2_redirect.html")
