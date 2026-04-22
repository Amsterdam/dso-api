from importlib.metadata import version

from django.http import HttpRequest
from packaging.version import parse
from schematools.contrib.django.models import Profile
from schematools.permissions import UserScopes
from schematools.permissions.auth import RLA_SCOPE

from dso_api.dbroles import DatabaseRoles


class AuthMiddleware:
    """
    Assigns `user_scopes` to request, for easy access.
    """

    def __init__(self, get_response):
        self._get_response = get_response
        # Load the profiles once on startup of the application (just like datasets are read once).
        self._all_profiles = [p.schema for p in Profile.objects.all()]
        # Row level auth requires schema-tools>=8.7.0
        RLA_NEEDED_VERSION = parse("8.7.1")
        has_rla_feature = parse(version("amsterdam-schema-tools")) >= RLA_NEEDED_VERSION
        self.feature_scopes = [RLA_SCOPE] if has_rla_feature else []

    def __call__(self, request: HttpRequest):
        # OPTIONS requests have no get_token_scopes, but don't need a UserScopes either.
        if request.method != "OPTIONS":
            # get_token_scopes should be set by authorization_django. We use it,
            # instead of is_authorized_for, to get more control over authorization
            # checks and to enable more precise logging.
            # get_token_scopes is a data attribute, not a method.
            scopes = set(request.get_token_scopes or [])
            scopes.update(self.feature_scopes)
            request.user_scopes = UserScopes(request.GET, scopes, self._all_profiles)

        # Extract user/system account id to be used for logging
        account = None
        if "email" in request.get_token_claims:  # User email in Keycloak tokens
            account = request.get_token_claims["email"]
        elif "upn" in request.get_token_claims:  # User email in Entra ID tokens
            account = request.get_token_claims["upn"]
        elif "appid" in request.get_token_claims:  # Appid for Entra ID system accounts
            account = request.get_token_claims["appid"]
        # If none of the above, fall back to token subject
        else:
            account = request.get_token_subject
        if account:
            request.account_id = account

        # Set database role with account id and issuer
        issuer = None
        if getattr(request, "get_token_claims", None) and "iss" in request.get_token_claims:
            issuer = request.get_token_claims["iss"]
        DatabaseRoles.set_end_user(account, issuer)

        return self._get_response(request)
