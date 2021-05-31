from django.shortcuts import render


def oauth2_redirect(request):
    return render(request, template_name="dso_api/dynamic_api/oauth2_redirect.html")
