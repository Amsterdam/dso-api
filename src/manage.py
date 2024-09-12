#!/usr/bin/env python
import os
import sys
import warnings
import logging
from opentelemetry.instrumentation.django import DjangoInstrumentor

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dso_api.settings")

    def response_hook(span, request, response):
        if span and span.is_recording():
            email = request.get_token_subject
            if getattr(request, "get_token_claims", None) and "email" in request.get_token_claims:
                email = request.get_token_claims["email"]
                span.set_attribute("user.AuthenticatedId", email)

    # Instrument Django app
    DjangoInstrumentor().instrument(response_hook=response_hook)
    print("django instrumentor enabled")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Reloading models is not advised.*")
        execute_from_command_line(sys.argv)
