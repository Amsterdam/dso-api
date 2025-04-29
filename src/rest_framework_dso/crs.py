"""This expose common projections for Dutch GIS systems.

.. note:
   Currently this package just imports the :class:`CRS` and :attr:`WGS84` objects
   from *django-gisserver* pretending that they exist here.
   This needs to be copied when publishing :mod:`rest_framework_dso` as a separate library.
"""

from gisserver.geometries import CRS, CRS84, WGS84

__all__ = [
    "CRS",
    "CRS84",
    "WGS84",
    "RD_NEW",
    "DEFAULT_CRS",
    "OTHER_CRS",
    "ALL_CRS",
]

# Common projections for Dutch GIS systems:

#: Amersfoort / RD New, see https://epsg.io/28992
RD_NEW = CRS.from_string("urn:ogc:def:crs:EPSG::28992")

#: Spherical Mercator (Google Maps, ...), see https://epsg.io/3857
WEB_MERCATOR = CRS.from_string("urn:ogc:def:crs:EPSG::3857")

#: European Terrestrial Reference System 1989, see https://epsg.io/4258
ETRS89 = CRS.from_string("urn:ogc:def:crs:EPSG::4258")

#: The default suggested CRS (e.g for use in WFS)
DEFAULT_CRS = RD_NEW

#: Other suggested CRS's (e.g for use in WFS)
OTHER_CRS = [WGS84, WEB_MERCATOR, ETRS89]

#: All coordinate reference systems exposed by this file.
ALL_CRS = frozenset([DEFAULT_CRS] + OTHER_CRS)
