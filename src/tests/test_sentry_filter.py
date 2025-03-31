import pytest
from django.conf import settings

from dso_api.sentry import before_send


def _get_event(request_url):
    """Get a minimal dummy event."""
    return {"request": {"url": request_url}}


@pytest.mark.parametrize(
    "blocked_paths,request_url,is_blocked",
    [
        ([], "http://api.example.com/v1/gebieden/buurten", False),
        (["v1/gebieden"], "http://api.example.com/v1/gebieden/buurten", True),
        (["v1/gebieden", "v1/brk"], "http://api.example.com/v1/gebieden/buurten", True),
        (["v1/gebieden"], "http://api.example.com/v1/brk/kadastraleobjecten", False),
        (["v1/gebieden"], "http://api.example.com/v1/foo/../gebieden/buurten", True),
        (["v1/gebieden"], "http://api.example.com/v1//gebieden/buurten", True),
    ],
)
def test_sentry_event_filter(monkeypatch, blocked_paths, request_url, is_blocked):
    monkeypatch.setattr(settings, "SENTRY_BLOCKED_PATHS", blocked_paths)
    assert (before_send(_get_event(request_url), {}) is None) is is_blocked
