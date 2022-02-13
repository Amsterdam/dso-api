from os.path import normpath
from typing import Any, Optional
from urllib.parse import urlparse

from django.conf import settings

# The makers of sentry only have internal types (in `_types`)
# those are not considered stable atm, so we define
# our own aliases for now.
Event = 'dict[str, Any]'
Hint = 'dict[str, Any]'


def before_send(event: Event, hint: Hint) -> Optional[Event]:
    """Filters events before they are sent to the Sentry server."""

    path = urlparse(event["request"]["url"]).path

    if any(
        path_fragment in normpath(path)
        for path_fragment in settings.SENTRY_BLOCKED_PATHS
        if path_fragment
    ):
        return None
    return event
