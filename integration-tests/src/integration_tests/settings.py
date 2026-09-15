import os
from pathlib import Path

from integration_tests.exceptions import ImproperlyConfigured

CLOUD_ENV = os.environ.get("CLOUD_ENV", "default").lower()
DATAPUNT_API_URL = os.environ.get("DATAPUNT_API_URL", "http://localhost:8090")
DEBUG = os.environ.get("DEBUG", False)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()
ALLOWED_FAILURES = int(os.environ.get("ALLOWED_FAILURES", 0))

if CLOUD_ENV.startswith("azure"):
    TOKEN = None

    # On Azure we'll get a token from the app registration
    TENANT_ID = os.environ.get("TENANT_ID")
    AUDIENCE = os.environ.get("AUDIENCE")
    CLIENT_ID = os.environ.get("CLIENT_ID")
    SCOPE = os.environ.get("SCOPE", f"{AUDIENCE}/.default")

    _USE_SECRET_STORE = Path("/mnt/secrets-store").exists()

    if _USE_SECRET_STORE:
        CLIENT_SECRET = Path("/mnt/secrets-store/dso-integration-tests-client-secret").read_text()
    else:
        CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

    if not TENANT_ID:
        raise ImproperlyConfigured("Missing TENTANT_ID environment variable")
    if not AUDIENCE:
        raise ImproperlyConfigured("Missing AUDIENCE environment variable")
    if not CLIENT_ID:
        raise ImproperlyConfigured("Missing CLIENT_ID environment variable")
    if not CLIENT_SECRET:
        raise ImproperlyConfigured("Missing CLIENT_SECRET environment variable")
else:
    # For local development we use a token from the environment
    TOKEN = os.environ.get("TOKEN")
