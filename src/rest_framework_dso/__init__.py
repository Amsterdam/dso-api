"""This package holds a reference implementation for DSO-compliant API's in Python
using Django-Rest-Framework.

.. note::
    DSO = Digitaal Stelsel Omgevingswet.
    This is a Dutch standard for API's for the government in The Netherlands:
    https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/
    This is also updated using the "NL Designrules":
    https://docs.geostandaarden.nl/api/API-Strategie-ext/

Implemented bits:

* HAL links ``{"_links": {"self": {"href": ..., "title": ...}}}``
* The ``?_expand=true`` option to sideload all related objects.
* The ``?_expandScope=relation1,relation2`` to receive related objects in the same response.
* The ``?_fields=...`` option to limit which fields to return,\
  with the DSO 1.0 ``?fields=..`` as fallback.
* The ``?_sort=...`` parameter, and the DSO 1.0 ``?sorteer=..`` as fallback
* No envelope for single-object / detail views.

Additionally:

* We support ``?_pageSize=...`` to change the REST page size, with ``?page_size=..`` as fallback.
* We support ``?_format=..`` to request other output formats\
  (e.g. ``json``, ``geojson`` or ``csv``).
* We support ``?_csv_header=..`` to request alternative headers\
  (e.g. ``none``, ``titles``).
* We support ``?_csv_separator=..`` to request a semicolon as delimiter, with a standard comma\
  as fallback.

Mandatory settings to activate these classes by default:

.. code-block:: python

    REST_FRAMEWORK = dict(
        PAGE_SIZE=20,
        MAX_PAGINATE_BY=20,
        DEFAULT_PAGINATION_CLASS="rest_framework_dso.pagination.DSOPageNumberPagination",
        DEFAULT_SCHEMA_CLASS="rest_framework_dso.openapi.DSOAutoSchema",
        DEFAULT_RENDERER_CLASSES=[
            "rest_framework_dso.renderers.HALJSONRenderer",
            "rest_framework_dso.renderers.CSVRenderer",
            "rest_framework_dso.renderers.GeoJSONRenderer",
            "rest_framework_dso.renderers.BrowsableAPIRenderer",  # Optional
        ],
        DEFAULT_FILTER_BACKENDS=[
            "django_filters.rest_framework.backends.DjangoFilterBackend",
        ],
        EXCEPTION_HANDLER="rest_framework_dso.views.exception_handler",
        COERCE_DECIMAL_TO_STRING=True,
        URL_FORMAT_OVERRIDE="_format",  # use ?_format=.. instead of ?format=..
    )

To write fields as "camelCase" either define the serializer as such,
or use *djangorestframework-camel-case* which rewrites the output.
"""
