"""The "dynamic API" provides the REST API support for dynamically generated models.

The models themselves are constructed from JSON Schema files by :mod:`schematools.contrib.django`.
Originally, that functionality was part of this project too, but it was moved to a library
so other projects can use that functionality too.

The dynamic API bridges both the generic DSO functionality from :mod:`rest_framework_dso`
with the additional policy information from the JSON Schema files by :mod:`schematools.types`.

.. graphviz::

   digraph foo {

      drf [label="Django Rest Framework"]
      rest_framework_dso [label="rest_framework_dso"]
      dynamic [label="dso_api.dynamic_api"]
      schematools_contrib_django [label="schematools.contrib.django"]

      schematools_contrib_django -> dynamic
      drf -> rest_framework_dso
      rest_framework_dso -> dynamic
   }

|
"""
