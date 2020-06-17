import re

RE_CAMELIZE = re.compile(r"[a-z0-9]_[a-z0-9]")


def _underscore_to_camel(match):
    chars = match.group()  # take complete match, it's only 3 chars
    return chars[0] + chars[2].upper()


def snake_to_camel_case(key: str) -> str:
    """Convert snake_case to camelCase.

    This logic is based on djangorestframework-camel-case.
    instead of rewriting the response dynamically, this package changes the
    field names at creation time. This is more efficient, and avoids patching
    various other places that would otherwise response to snake_case input.
    """
    return re.sub(RE_CAMELIZE, _underscore_to_camel, key)
