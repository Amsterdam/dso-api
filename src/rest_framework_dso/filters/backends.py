import math
import re
from typing import Optional

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from django_filters.rest_framework import DjangoFilterBackend
from gisserver.geometries import CRS
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from schematools.utils import to_snake_case

from .filtersets import DSOFilterSet


class DSOFilterBackend(DjangoFilterBackend):
    """DSF fields filter.

    This loads the filterset logic of django-filter into the
    REST Framework :class:`~rest_framework.generics.GenericAPIView`.
    The real work is performed in the custom :class:`~rest_framework_dso.filters.DSOFilterSet`
    subclass that is configured for that particular view.

    Usage in views::

        class View(GenericAPIView):
            filter_backends = [filters.DSOFilterBackend]
            filterset_class = ... # subclass of DSOFilterSet

    The ``filterset_class`` defines how each querystring field is parsed and processed.
    """

    filterset_base = DSOFilterSet

    def to_html(self, request, queryset, view):
        """See https://github.com/tomchristie/django-rest-framework/issues/3766.

        This prevents DRF from generating the filter dropdowns
        (which can be HUGE in our case)
        """
        return ""

    _NON_FIELDS = {"_fields", "_format", "_sort", "_pageSize", "_page_size"}

    def is_unfiltered(self, request):
        # If there are request parameters (except for this hard-coded exclude list),
        # they are assumed to be filters.
        return request.GET.keys() <= self._NON_FIELDS

    def get_filterset(self, request, queryset, view):  # noqa: C901
        # Optimization: avoid creating the whole filterset, when nothing will be filtered.
        # This also avoids a deepcopy of the form fields.
        if self.is_unfiltered(request):
            return None

        filterset = super().get_filterset(request, queryset, view)
        for name, value in filterset.data.items():
            if (
                name.endswith("[contains]")
                and name in filterset.base_filters
                and filterset.base_filters[name].__class__.__name__.endswith("GeometryFilter")
            ):
                value = parse_point(value, request.accept_crs)
                new_data = filterset.data.copy()
                new_data[name] = value
                filterset.data = new_data

        return filterset


class DSOOrderingFilter(OrderingFilter):
    """DRF Ordering filter, following the DSO spec.

    This adds an ``?_sort=<fieldname>,-<desc-fieldname>`` option to the view.
    On the view, an ``view.ordering_fields`` attribute may limit which fields
    can be used in the sorting. By default, it's all serializer fields.

    Usage in views::

        class View(GenericAPIView):
            filter_backends = [filters.DSOOrderingFilter]
    """

    ordering_param = "_sort"

    def get_ordering(self, request, queryset, view):
        if self.ordering_param not in request.query_params:
            # Allow DSO 1.0 Dutch "sorteer" parameter
            # Can adjust 'self' as this instance is recreated each request.
            if "sorteer" in request.query_params:
                self.ordering_param = "sorteer"

        ordering = super().get_ordering(request, queryset, view)
        if ordering is None:
            return ordering

        # Convert identifiers to snake_case, preserving `-` (descending sort).
        return [
            "-" + to_snake_case(part[1:]) if part.startswith("-") else to_snake_case(part)
            for part in ordering
        ]

    def remove_invalid_fields(self, queryset, fields, view, request):
        """Raise errors for invalid parameters instead of silently dropping them."""
        cleaned = super().remove_invalid_fields(queryset, fields, view, request)
        if cleaned != fields:
            invalid = ", ".join(sorted(set(fields).difference(cleaned)))
            raise ValidationError(f"Invalid sort fields: {invalid}", code="order-by")
        return cleaned


def parse_point(value: str, crs: Optional[CRS]) -> GEOSGeometry:
    x, y = _parse_point(value)
    srid = crs.srid if crs else None
    x_lon, y_lat, srid = _validate_convert_x_y(x, y, srid)
    if srid in (4326, 28992) and (x_lon is None or y_lat is None):
        raise ValidationError(f"Invalid x,y values : {x},{y} in {value!r}")
    try:
        return GEOSGeometry(f"POINT({x_lon} {y_lat})", srid)
    except GEOSException as e:
        raise ValidationError(f"Invalid x,y values {x},{y} with SRID {srid}") from e


def _parse_point(value: str) -> 'tuple[float, float]':
    if m1 := re.match(r"([-+]?\d*(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)", value):
        x = m1.group(1)
        y = m1.group(2)
    elif m1 := re.match(r"POINT\(([-+]?\d+(?:\.\d+))? ([-+]?\d+(?:\.\d+))\)", value):
        x = m1.group(1)
        y = m1.group(2)
    else:
        raise ValidationError(f"not a valid point: {value!r}")

    try:
        x, y = float(x), float(y)
    except ValueError as e:
        raise ValidationError(f"not a valid point: {value!r}") from e

    # We can get infinities despite the regexp, e.g., float("1" * 310) == float("inf").
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValidationError(f"not a valid point: {value!r}")

    return x, y


def _valid_rd(x: float, y: float) -> bool:
    """
    Check valid RD x, y coordinates
    """

    rd_x_min = 0
    rd_y_min = 300000
    rd_x_max = 280000
    rd_y_max = 625000

    return rd_x_min <= x <= rd_x_max and rd_y_min <= y <= rd_y_max


def _valid_lat_lon(lat: float, lon: float) -> bool:
    """
    Check if lat/lon is in the Netherlands bounding box
    """
    lat_min = 50.803721015
    lat_max = 53.5104033474
    lon_min = 3.31497114423
    lon_max = 7.09205325687

    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _validate_convert_x_y(
    x: float, y: float, srid: Optional[int]
) -> 'tuple[float, float, Optional[int]]':
    if srid is None or srid == 4326:
        if _valid_lat_lon(x, y):
            return y, x, 4326  # x and y swapped.
        elif _valid_lat_lon(y, x):
            return x, y, 4326
    if srid is None or srid == 28992:
        if _valid_rd(x, y):
            return x, y, 28992
    elif srid not in (28992, 4326):
        return x, y, srid
    return None, None, srid
