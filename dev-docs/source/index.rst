DSO-API's Developer Documentation
=================================

This documentation gives an introduction behind the scenes of the DSO-API.
For end-user documentation, see https://api.data.amsterdam.nl/v1/docs/.

A Brief Introduction
--------------------

The DSO-API project was started by the Gemeente Amsterdam to create consistent API interfaces.
Before DSO-API existed, each dataset had to be exposed by a standalone project.
This caused inconsistencies and maintenance issues.

To solve that problem, the dataset definitions are decoupled from the code.
The dataset definitions are written in an an extended JSON Schema definition (called "Amsterdam Schema"),
which is loaded on startup. This way, all dataset are exposed in the same way.

Multiple datasets can be loaded in the same server instance. This turns the project into a central API-server,
that hosts multiple datasets and even supports interlinking relations between the datasets.

.. note::
    The name "DSO" comes from `Digitaal Stelsel Omgevingswet`_ and describes
    the design and guidelines for JSON-based API's by government agencies in The Netherlands.
    Using this format, clients can to communicate with different JSON API's in a generic and consistent manner.

Aside from REST endpoints, the datasets are also exposed as WFS and MVT (Mapbox Vector Tile) endpoints.
The REST endpoints follow the DSO (`Digitaal Stelsel Omgevingswet`_) guidelines.
Most guidelines from DSO are based on the expired `HAL-JSON API style`_.

Project Dependencies:
---------------------

A simplified diagram of the main project dependencies:

.. graphviz::

   digraph foo {

      django [label="Django"]
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

.. toctree::
   :maxdepth: 1
   :caption: Topics:

   layers
   rest_framework
   features
   dynamic_models
   dynamic_api
   remote
   temporal
   streaming
   auth
   openapi
   schemas
   dataset_versioning
   wfs
   environment
   compliance

.. toctree::
   :maxdepth: 1
   :caption: HOW-TO:

   howto/install
   howto/pip
   howto/testruns
   howto/schemas
   howto/openapi
   howto/azure_oauth

.. toctree::
   :caption: API Documentation:
   :maxdepth: 2

   api/dso_api.dynamic_api
   api/rest_framework_dso
   api/schematools
   api/schematools.contrib.django

.. _Digitaal Stelsel Omgevingswet: https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/
.. _HAL-JSON API style: https://datatracker.ietf.org/doc/html/draft-kelly-json-hal-08
