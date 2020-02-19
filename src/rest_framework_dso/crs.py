"""Expose common projections for Dutch GIS systems

NOTE: the CRS class should be imported when publishing this as a separate library.
"""
from gisserver.types import CRS, WGS84

__all__ = [
    "CRS",
    "WGS84",
    "RD_NEW",
    "WEB_MERCATOR",
    "ETRS89",
    "DEFAULT_CRS",
    "OTHER_CRS",
    "ALL_CRS",
]

# Common projections for Dutch GIS systems:
RD_NEW = CRS.from_string("EPSG:28992")  # Amersfoort / RD New
WEB_MERCATOR = CRS.from_string("EPSG:3857")  # Spherical Mercator (Google Maps, ...)
ETRS89 = CRS.from_string("EPSG:4258")  # European Terrestrial Reference System 1989

DEFAULT_CRS = RD_NEW
OTHER_CRS = [WGS84, WEB_MERCATOR, ETRS89]
ALL_CRS = set([DEFAULT_CRS] + OTHER_CRS)
