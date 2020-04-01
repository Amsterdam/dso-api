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
    layer = ds[0]
    for feature in layer:
        callback(feature)


def get_geotype(wkt, geotype):  # noqa: C901
    if not wkt:
        return None

    geom = GEOSGeometry(wkt)
    if geom:
        if geotype == "multipolygon":
            if isinstance(geom, Polygon):
                geom = MultiPolygon(geom)
            elif isinstance(geom, MultiPolygon):
                pass
            else:
                geom = None
        elif geotype == "polygon" and isinstance(geom, Polygon):
            pass
        elif geotype == "point" and isinstance(geom, Point):
            pass
        elif geotype == "multiline":
            if isinstance(geom, LineString):
                geom = MultiLineString(geom)
            elif isinstance(geom, MultiLineString):
                pass
    return geom
