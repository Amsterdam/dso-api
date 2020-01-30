"""Reference implementation for DSO-compliant API's in Python with Django-Rest-Framework.

DSO = Digitaal Stelsel Omgevingswet.
This is a Dutch standard for API's for the government in The Netherlands:
https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/

Implemented:

* HAL links {"_links": {"self": {"href": ..., "title": ...}}}
* HAL ``?expand=field1,field2`` -> gives ``_embedded`` field in response.
* The ``?expand=true`` option to expand all fields
* No envelope for single-object / detail views.

Via other packages:

* Enforce fields in camelCase -> use djangorestframework-camel-case

Not implemented:

* ?fields=field1.subfield
* ?sorteer=-field  (ordering)
* ?zoek=urgent (search queries, including ``*`` and ``?`` wildcards for single words)
* GeoJSON support.

Extra recommendations:

* Use base64-encoded UUID's (=22 characters).
"""
