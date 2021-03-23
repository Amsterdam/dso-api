DSO-API's Developer Documentation
=================================

This documentation gives an introduction behind the scenes of the DSO-API.
For end-user documentation, see https://api.data.amsterdam.nl/v1/docs/.

The DSO-API project is designed as a central API-server component,
which hosts multiple datasets based on an extended JSON schema definition (called "Amsterdam Schema").
The datasets are exposed over both REST and WFS endpoints.
The REST endpoints follow the DSO (Digitaal Stelsel Omgevingswet) which is the recommended design
for government API's. Most logic of DSO is based on the HAL-JSON API style.

.. toctree::
   :maxdepth: 1
   :caption: Topics:

   features
   dynamic_models
   dynamic_api
   layers
   wfs
   remote
   auth
   environment
   compliance

.. toctree::
   :caption: API Documentation:
   :maxdepth: 4

   api/dso_api.dynamic_api
   api/rest_framework_dso
   api/schematools
   api/schematools.contrib.django

A simplified diagram of the main project dependencies:

.. graphviz::

   digraph foo {

      dso_api [label="DSO-API"]
      drf [label="Django Rest Framework"]
      wfs [label="django-gisserver (WFS)"]

      schematools_contrib_django [label="schematools.contrib.django"]

      ams [label="Amsterdam Schema", shape=note]
      airflow [label="Airflow", shape=cylinder]

      schematools_contrib_django -> dso_api
      django -> drf
      django -> wfs
      wfs -> dso_api
      drf -> dso_api
      django -> schematools_contrib_django
      schematools -> schematools_contrib_django
      ams -> dso_api [style=dotted, label="import"]
      airflow -> dso_api [style=dotted, label="data"]
   }
