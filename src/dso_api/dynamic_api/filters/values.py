"""Conversion of query-string values to Python types."""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.gis.gdal.error import GDALException
from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point
from django.contrib.gis.geos.prototypes import geom  # noqa: F401
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from gisserver.geometries import CRS
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Don't want Decimal("NaN"), Decimal("-inf") or '0.321000e+2' to be accepted.
RE_DECIMAL = re.compile(r"^[0-9]+(\.[0-9]+)?$")
AMSTERDAM_BOUNDS = [4.72876, 52.2782, 5.07916, 52.4311]
DAM_SQUARE = [4.8925627, 52.3731139, 14]  # Zoom = 14


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
        # while this uses strptime(), it only takes the date, which has no tzinfo
        return datetime.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007
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
            # while this uses strptime(), it only takes the time, so no tzinfo neeed.
            return datetime.strptime(value, format).time()  # noqa: DTZ007
        except ValueError:
            pass

    raise ValidationError(_("Enter a valid time."), code="invalid")


def str2geo(value: str, crs: CRS | None = None) -> GEOSGeometry:
    """Convert a string to a geometry object.
    Supports Point, Polygon and MultiPolygon objects in WKT or GeoJSON format.

    Args:
        value: String representation of geometry (WKT, GeoJSON, or x,y format)
        crs: Optional coordinate reference system

    Returns:
        GEOSGeometry object
    """
    srid = crs.srid if crs else 4326
    stripped_value = value.lstrip()
    # Try parsing as GeoJSON first
    if stripped_value.startswith(("{", "[")):
        return _parse_geojson(stripped_value, srid)

    # Try x,y format if it looks like two numbers separated by a comma
    if stripped_value.startswith(("POINT", "POLYGON", "MULTIPOLYGON")):
        return _parse_wkt_geometry(stripped_value, srid)
    else:
        return _parse_point_geometry(stripped_value, srid)


def _parse_geojson(value: str, srid: int | None) -> GEOSGeometry:
    """Parse GeoJSON string and validate basic structure.

    Args:
        value: GeoJSON string

    Returns:
        GEOSGeometry object

    Raises:
        ValidationError: If GeoJSON is invalid
    """
    try:
        return GEOSGeometry(value, srid)
    except (GEOSException, ValueError, GDALException) as e:
        raise ValidationError(f"Invalid GeoJSON: {e}") from e


def _parse_wkt_geometry(value: str, srid: int | None) -> GEOSGeometry:
    """Parse and validate a WKT geometry string.

    Args:
        value: WKT geometry string
        srid: Optional spatial reference identifier

    Returns:
        Validated GEOSGeometry object

    Raises:
        ValidationError: If geometry is invalid or unsupported type
    """
    try:
        geom = GEOSGeometry(value, srid)
    except (GEOSException, ValueError) as e:
        raise ValidationError(f"Invalid WKT format in {value}. Error: {e}") from e

    if geom.geom_type not in ("Point", "Polygon", "MultiPolygon"):
        raise ValidationError(
            f"Unsupported geometry type: {geom.geom_type}. "
            "Only Point, Polygon and MultiPolygon are supported."
        )

    # check if the geometry is within the Netherlands, only warn if not
    if geom.geom_type in ("Polygon", "MultiPolygon") and not _validate_bounds(geom, srid):
        logger.warning("Geometry bounds outside Netherlands")

    # Try parsing as point
    if geom.geom_type == "Point":
        try:
            return _validate_point_geometry(geom, srid)
        except ValidationError as e:
            raise ValidationError(f"Invalid point format in {value}. Error: {e}") from e

    return geom


def _parse_point_geometry(value: str, srid: int | None) -> GEOSGeometry:
    """Parse and validate a point in x,y format.

    Args:
        value: String in "x,y" format
        srid: Optional spatial reference identifier

    Returns:
        Validated Point geometry

    Raises:
        ValidationError: If point format or coordinates are invalid
    """
    try:
        x, y = _parse_point(value)
        return _validate_correct_x_y(x, y, srid)
    except ValueError as e:
        raise ValidationError(f"Invalid point format in {value!r}. Error: {e}") from e


def _validate_point_geometry(point: GEOSGeometry, srid: int | None) -> GEOSGeometry:
    """Validate a point geometry's coordinates.

    Args:
        point: Point geometry to validate
        srid: Optional spatial reference identifier

    Returns:
        Validated point geometry

    Raises:
        ValidationError: If coordinates are invalid
    """
    try:
        x, y = point.coords
        return _validate_correct_x_y(x, y, srid)
    except (ValueError, GEOSException) as e:
        raise ValidationError(f"Invalid point coordinates {point.coords} with SRID {srid}") from e


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


def _validate_bounds(geom: GEOSGeometry, srid: int | None) -> bool:  # noqa: F811
    """Validate if geometry bounds are within Netherlands extent.
    Returns True if geometry is within bounds, False otherwise.

    Args:
        geom: GEOSGeometry object to validate
        srid: Spatial reference system identifier

    Returns:
        bool: True if geometry is within Netherlands bounds, False otherwise
    """
    bounds = geom.extent  # (xmin, ymin, xmax, ymax)
    corners = [(bounds[0], bounds[1]), (bounds[2], bounds[3])]  # SW, NE corners

    if srid == 4326:
        return _validate_wgs84_bounds(corners)
    elif srid == 28992:
        return _validate_rd_bounds(corners)
    return True  # If srid is not 4326 or 28992, assume valid


def _validate_wgs84_bounds(corners: list[tuple[float, float]]) -> bool:
    """Check if WGS84 coordinates are within Netherlands bounds.
    Note: Expects (x,y) format, will swap to (lat,lon) internally.
    """
    return all(_valid_nl_wgs84(y, x) for x, y in corners)


def _validate_rd_bounds(corners: list[tuple[float, float]]) -> bool:
    """Check if RD coordinates are within Netherlands bounds."""
    return all(_valid_rd(x, y) for x, y in corners)


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
