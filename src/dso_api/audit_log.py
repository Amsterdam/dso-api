"""The audit log. Performs structured logging.

The intended usage of this module is to import it, then pretend it is a logger object.

Configuration lives in settings.py.
"""

import json
import logging
from datetime import datetime
from typing import Any, Iterable


def _to_jsonable(x: Any) -> Any:
    """Convert x to a JSON'able object. Default function for JSONEncoder."""
    if isinstance(x, Iterable):
        return tuple(x)
    # Make sure everything is encodable by taking the repr.
    return repr(x)


_encoder = json.JSONEncoder(default=_to_jsonable)

_logger = logging.getLogger("dso_api.audit")


def _log(msg):
    msg["audit"] = True
    msg["name"] = "dso_api.audit"
    msg["time"] = datetime.now().isoformat()
    _logger.info(_encoder.encode(msg))


def info(**kwargs):
    kwargs["level"] = "INFO"
    _log(kwargs)
