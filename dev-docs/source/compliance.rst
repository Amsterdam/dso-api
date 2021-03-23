Standards Compliance
====================

REST API
--------

The DSO-API follows the guidelines from DSO (`Digitaal Stelsel Omgevingswet <https://aandeslagmetdeomgevingswet.nl/>`_).
They define the API design rules for government based API's in The Netherlands:

https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/

We also confirm with the "NL Designrules", which tries to update the DSO 2 standard to a living document:
https://docs.geostandaarden.nl/api/API-Strategie-ext/

The standards follow an "apply or explain" approach (in Dutch: "pas toe of leg uit"),
where implementations can opt-in to follow more rules,
or have to explain very well why they've deviated from them.

The following logic is implemented by the :mod:`rest_framework_dso` package:

* HAL links ``{"_links": {"self": {"href": ..., "title": ...}}}``
* The ``?_expand=true`` option to sideload all related objects.
* The ``?_expandScope=relation1,relation2`` to receive related objects in the same response.
* The ``?_fields=...`` option to limit which fields to return, with the DSO 1.0 ``?fields=..`` as fallback.
* The ``?_sort=...`` parameter, and the DSO 1.0 ``?sorteer=..`` as fallback
* No envelope for single-object / detail views.

Additionally:

* We support ``?_pageSize=...`` to change the REST page size, with ``?page_size=..`` as fallback.
* We support ``?_format=..`` to request other output formats (e.g. ``json``, ``geojson`` or ``csv``)
* We support temporal filtering with :samp:`?geldigOp={date}`.
* Fields are written as "camelCase"

Not implemented (yet):

* Subfields: ``?_fields=field1.subfield``
* Wildcard search with ``?_find=...``
* Queries with GeoJSON POST requests.


WFS Endpoints
-------------

The WFS endpoint implements most of the WFS 2.0 Basic Conformance level,
and some older WFS 1.0 filter syntax which is still used by clients.
This allows applications like QGis to work properly with the endpoints.
Technical details can be found in
the `django-gisserver documentation <https://django-gisserver.readthedocs.io/en/latest/compliance.html>`_.
