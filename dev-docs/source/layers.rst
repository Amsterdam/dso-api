Layers of Code
==============

The code of DSO-API has the following layers:

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

The :mod:`dso_api.dynamic_api` provides the dynamic API.
For this, it uses the datasets definitions that :mod:`schematools.contrib.django` provides.

REST API Logic
--------------

The REST API code is based on Django Rest Framework. The generic DSO compatibility layer is
implemented in the :mod:`rest_framework_dso` package, so it could be moved out to a official PyPI package.
On top of this, the specific logic to generate the API is implemented in the :mod:`dso_api.dynamic_api` package.

The Schematools Package
-----------------------

The :mod:`schematools` package fulfills a special role. It contains all fundamental parts
that can be shared with other applications. Specifically of interest are:

* :mod:`schematools.types` contains Python wrappers for the Amsterdam Schema file format.
* :mod:`schematools.contrib.django` stores those schema definitions into Django models.

The ``schematools`` package also provides a CLI: ``schema`` with various useful command-line tools such as:

* ``schema import geojson ...``
* ``schema import ndjson ...``
* ``schema introspect db ...``
* ``schema introspect geojson ...``

More information can be found using ``schema --help`` and checking
the `README <https://github.com/Amsterdam/schema-tools/blob/master/README.md>`_ file.
