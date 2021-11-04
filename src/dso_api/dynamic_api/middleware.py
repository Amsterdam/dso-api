from django.utils.deprecation import MiddlewareMixin
from schematools.contrib.django.models import Profile
from schematools.permissions import UserScopes


class DatasetMiddleware(MiddlewareMixin):
    """
    Assign `dataset` to request, for easy access.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        # Load the profiles once on startup of the application (just like datasets are read once).
        self.all_profiles = [p.schema for p in Profile.objects.all()]

    def process_request(self, request):
        """
        This method installs the `user_scopes` for the OAS views.
        """

        # get_token_scopes should be set by authorization_django. We use it,
        # instead of is_authorized_for, to get more control over authorization
        # checks and to enable more precise logging.

        if request.method == "OPTIONS":
            # OPTIONS requests have no get_token_scopes, but don't need a UserScopes either.
            return

        # get_token_scopes is a data attribute, not a method.
        scopes = request.get_token_scopes
        request.user_scopes = UserScopes(request.GET, scopes, self.all_profiles)
