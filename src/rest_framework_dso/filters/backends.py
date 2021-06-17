import re

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from django_filters.rest_framework import DjangoFilterBackend
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

        # TODO: this needs to be moved to proper FilterField classes!
        filterset = super().get_filterset(request, queryset, view)
        for name, value in filterset.data.items():
            if (
                name.endswith("[contains]")
                and name in filterset.base_filters
                and filterset.base_filters[name].__class__.__name__.endswith("GeometryFilter")
            ):
                if value:
                    if m1 := re.match(r"([-+]?\d*(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)", value):
                        x = m1.group(1)
                        y = m1.group(2)
                    elif m1 := re.match(
                        r"POINT\(([-+]?\d+(?:\.\d+))? ([-+]?\d+(?:\.\d+))\)", value
                    ):
                        x = m1.group(1)
                        y = m1.group(2)
                    else:
                        continue
                    if x and y:
                        srid = request.accept_crs.srid if request.accept_crs else None
                        x_lon, y_lat, srid = _validate_convert_x_y(x, y, srid)
                        if srid in (4326, 28992) and (x_lon is None or y_lat is None):
                            raise ValueError(f"Invalid x,y values : {x},{y}")
                        # longitude, latitude for 4326 x,y otherwise
                        try:
                            value = GEOSGeometry(f"POINT({x_lon} {y_lat})", srid)
                        except GEOSException as e:
                            raise ValidationError(f"Invalid x,y values : {x},{y}") from e
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


def _valid_rd(x, y):
    """
    Check valid RD x, y coordinates
    """

    rd_x_min = 0
    rd_y_min = 300000
    rd_x_max = 280000
    rd_y_max = 625000

    if not rd_x_min <= x <= rd_x_max:
        return False

    if not rd_y_min <= y <= rd_y_max:
        return False

    return True


def _valid_lat_lon(lat, lon):
    """
    Check if lat/lon is in the Netherlands bounding box
    """
    lat_min = 50.803721015
    lat_max = 53.5104033474
    lon_min = 3.31497114423
    lon_max = 7.09205325687

    if not lat_min <= lat <= lat_max:
        return False

    if not lon_min <= lon <= lon_max:
        return False

    return True


def _validate_convert_x_y(x, y, srid):
    fx = float(x)
    fy = float(y)
    x_lon = y_lat = None
    if not srid or srid == 4326:
        if _valid_lat_lon(fx, fy):
            x_lon = y
            y_lat = x
            srid = 4326
        elif _valid_lat_lon(fy, fx):
            x_lon = x
            y_lat = y
            srid = 4326
    if not srid or srid == 28992:
        if _valid_rd(fx, fy):
            x_lon = x
            y_lat = y
            srid = 28992
    elif srid not in (28992, 4326):
        x_lon = x
        y_lat = y
    return x_lon, y_lat, srid
