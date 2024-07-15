"""Conversion of query-string values to Python types."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from gisserver.geometries import CRS
from rest_framework.exceptions import ValidationError

# Don't want Decimal("NaN"), Decimal("-inf") or '0.321000e+2' to be accepted.
RE_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")


def str2bool(value: str) -> bool:
    value = str(value).lower()
    if value in ("true", "1"):
        return True
    elif value in ("false", "0"):
        return False
    else:
        raise ValueError("expect true/false")


def str2number(value: str) -> Decimal:
    if not RE_DECIMAL.match(value):
        raise ValueError("expecting number")

    return Decimal(value)


def str2isodate(value: str) -> date | datetime | None:
    """Parse ISO date and datetime."""

    # Try parsing ISO date without time.
    # This is checked first, so the function can explicitly return a date object
    # for something that has no time at inputs, allowing to check against a complete day
    # instead of exactly midnight.
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try parsing full iso-8601 datetime (also works for date-only values in Django >= 4.x)
    try:
        result = parse_datetime(value)
        if result is not None:
            return result
    except ValueError:
        pass  # e.g. well formatted but invalid values

    raise ValidationError(_("Enter a valid ISO date-time, or single date."), code="invalid")


def str2time(value: str) -> time:
    """Parse a HH:MM:SS or HH:MM time formatted string."""
    for format in ("%H:%M:%S", "%H:%M", "%H:%M:%S.%f"):
        try:
            return datetime.strptime(value, format).time()
        except ValueError:
            pass

    raise ValidationError(_("Enter a valid time."), code="invalid")


def str2geo(value: str, crs: CRS | None = None) -> GEOSGeometry:
    """Convert a string to a geometry object.
    Currently only parses point objects.
    """
    srid = crs.srid if crs else None
    x, y = _parse_point(value)

    try:
        return _validate_correct_x_y(x, y, srid)
    except ValueError as e:
        raise ValidationError(f"{e} in {value!r}") from None
    except GEOSException as e:
        raise ValidationError(f"Invalid x,y values {x},{y} with SRID {srid}") from e


def _parse_point(value: str) -> tuple[float, float]:
    if m1 := re.match(r"([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)", value) or (
        m1 := re.match(r"POINT\(([-+]?\d+(?:\.\d+)?) ([-+]?\d+(?:\.\d+)?)\)", value)
    ):
        x = m1.group(1)
        y = m1.group(2)
    else:
        raise ValidationError(f"not a valid point: {value!r}")

    try:
        x, y = float(x), float(y)
    except ValueError as e:
        raise ValidationError(f"not a valid point: {value!r}") from e

    # We can get infinities despite the regexp.
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValidationError(f"not a valid point: {value!r}")

    return x, y


def _validate_correct_x_y(x: float, y: float, srid: int | None) -> Point:
    """Auto-correct various input variations."""

    # Try WGS84 coordinates
    if srid is None or srid == 4326:
        # latitude is the vertical axis, hence x/y are swapped.
        if _valid_nl_wgs84(x, y):
            return Point(y, x, srid=4326)
        elif _valid_nl_wgs84(y, x):
            return Point(x, y, srid=4326)

    # Try Dutch Rijksdriehoek coordinates
    if (srid is None or srid == 28992) and _valid_rd(x, y):
        return Point(x, y, srid=28992)

    # Leave other systems untouched
    if srid and srid not in (4326, 28992):
        return Point(x, y, srid=srid)

    raise ValueError(f"Invalid x,y values: {x},{y}")


def _valid_rd(x: float, y: float) -> bool:
    """Check if the X/Y fit in the Rijksdriehoek bounding box/coordinates."""
    return 0 <= x <= 280000 and 300000 <= y <= 625000


def _valid_nl_wgs84(latitude: float, longitude: float) -> bool:
    """See if latitude / longitude values fit in the Netherlands bounding box.
    Note that latitude is the vertical north-south axis,
    and longitude the horizontal west-east axis.
    """
    return (
        50.803721015 <= latitude <= 53.5104033474 and 3.31497114423 <= longitude <= 7.09205325687
    )
