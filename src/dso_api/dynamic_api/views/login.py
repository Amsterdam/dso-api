import base64
import hashlib
import random
import string
import requests
from urllib.parse import urlencode
from pprint import pprint
from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponse

BASE_MS_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/"
AUTHORIZE_URL = "{BASE_MS_URL}authorize?{params}"
TOKEN_URL = f"{BASE_MS_URL}/token"
SCOPES = "{CLIENT_ID}/.default"


def oauth2_redirect(request):
    return render(request, template_name="dso_api/dynamic_api/oauth2_redirect.html")


def generic_openapi(request):
    return render(request, template_name="dso_api/dynamic_api/generic_openapi.yaml")


def _get_redirect_uri():
    return "http://localhost:8000/hub/oauth_callback"