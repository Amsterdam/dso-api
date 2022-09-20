from django.http import HttpRequest
from schematools.contrib.django.models import Profile
from schematools.permissions import UserScopes

from dso_api.dbroles import DatabaseRoles


class AuthMiddleware:
    """
    Assigns `user_scopes` to request, for easy access.
    """

    def __init__(self, get_response):
        self._get_response = get_response
        # Load the profiles once on startup of the application (just like datasets are read once).
        self._all_profiles = [p.schema for p in Profile.objects.all()]

    def __call__(self, request: HttpRequest):
        # OPTIONS requests have no get_token_scopes, but don't need a UserScopes either.
        if request.method != "OPTIONS":
            # get_token_scopes should be set by authorization_django. We use it,
            # instead of is_authorized_for, to get more control over authorization
            # checks and to enable more precise logging.
            # get_token_scopes is a data attribute, not a method.
            scopes = request.get_token_scopes or []
            request.user_scopes = UserScopes(request.GET, scopes, self._all_profiles)

        # The token subject contains the username/email address of the user (on Azure)
        DatabaseRoles.set_end_user(request.get_token_subject)

        return self._get_response(request)
