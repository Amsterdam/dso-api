"""Reference implementation for DSO-compliant API's in Python with Django-Rest-Framework.

DSO = Digitaal Stelsel Omgevingswet.
This is a Dutch standard for API's for the government in The Netherlands:
https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/

Which is updated as "NL Designrules":
https://docs.geostandaarden.nl/api/API-Strategie-ext/

Implemented:

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
* To write fields as "camelCase" either define the serializer as such,
  or use djangorestframework-camel-case which rewrites the output.

Not implemented (yet):

* Subfields: ``?_fields=field1.subfield``
* Wildcard search with ``?_find=...``
* Queries with GeoJSON POST requests.

Extra recommendations:

* Use base64-encoded UUID's (=22 characters).

Mandatory settings:

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
"""
