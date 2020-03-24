import csv
import os.path

import sys
from django.contrib.gis.gdal import DataSource

from django.contrib.gis.geos import (
    GEOSGeometry,
    Polygon,
    MultiPolygon,
    Point,
    MultiLineString,
    LineString,
)

# sommige WKT-velden zijn best wel groot
csv.field_size_limit(sys.maxsize)


def process_wkt(path, filename, callback):
    """
    Processes a WKT file

    :param path: directory containing the file
    :param filename: name of the file
    :param callback: function taking an id and a geometry; called for every row
    """
    source = os.path.join(path, filename)
    with open(source) as f:
        rows = csv.reader(f, delimiter="|")
        for row in rows:
            callback(row[0], GEOSGeometry(row[1]))


def process_shp(path, filename, callback, encoding="ISO-8859-1"):
    """
    Processes a shape file

    :param path: directory containing the file
    :param filename: name of the file
    :param callback: function taking a shapefile record; called for every row
    :param encoding: optional encoding for the shapefile
    :return:
    """
    source = os.path.join(path, filename)
    ds = DataSource(source, encoding=encoding)
    lyr = ds[0]
    for feature in lyr:
        callback(feature)


def get_multipoly(wkt):
    if not wkt:
        return None

    geom = GEOSGeometry(wkt)

    if not geom:
        return None

    if isinstance(geom, Polygon):
        return MultiPolygon(geom)

    if isinstance(geom, Point):
        return None

    return geom


def get_poly(wkt):
    if not wkt:
        return None

    geom = GEOSGeometry(wkt)

    if geom and isinstance(geom, Polygon):
        return geom
    return None


def get_point(wkt):
    if not wkt:
        return None

    geom = GEOSGeometry(wkt)

    if geom and isinstance(geom, Point):
        return geom

    return None


def get_multiline(wkt):
    if not wkt:
        return None

    geom = GEOSGeometry(wkt)

    if not geom:
        return None

    if isinstance(geom, LineString):
        geom = MultiLineString(geom)

    if not isinstance(geom, MultiLineString):
        return None

    return geom
