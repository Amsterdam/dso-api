import json
import sys
import time
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management import BaseCommand
from jwcrypto.jwk import JWK
from jwcrypto.jwt import JWT


class Command(BaseCommand):
    """maketoken command: generates a JWT test token."""

    help = """Generate a JWT test token to test endpoints that are protected by an auth scope.
        See for usage: https://dso-api.readthedocs.io/en/latest/auth.html#testing
    """

    requires_system_checks = []

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Hook to add arguments."""
        parser.add_argument(
            "args", metavar="scopes", nargs="*", help="Scopes that will be added to the JWT token"
        )
        parser.add_argument(
            "--valid",
            default=None,
            type=int,
            help="Validity period, in seconds (default: forever)",
        )

    def handle(self, *args: str, **options: Any) -> None:
        """Main function of this command.

        It creates a JWT test token with the provided scopes and validity.
        """
        key = JWK(**json.loads(settings.DATAPUNT_AUTHZ["JWKS"])["keys"][0])
        scopes = list(set(args))
        now = int(time.time())
        claims = {
            "iat": now,
            "scopes": scopes,
            "sub": "test@tester.nl",
        }
        if options["valid"] is not None:
            claims["exp"] = now + options["valid"]
        token = JWT(header={"alg": "ES256", "kid": key.key_id}, claims=claims)
        token.make_signed_token(key)

        sys.stdout.write(token.serialize())
        sys.stdout.write("\n")
