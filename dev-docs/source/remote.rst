Remote Endpoints
================

Datasets can be configured to retrieve data from a remote endpoint,
as opposed to an internal database table. This is currently implemented by calling:

.. code-block:: console

    manage.py change_dataset $DATASET --endpoint-url=...

Remote endpoints have reduced functionality.
The following features are not available yet:

* Field reduction
* Expanding relations
* Filtering on relations
* WFS endpoints
* Export formats (e.g. CSV / GeoJSON)

In fact, the remote endpoints still behave mostly as a reverse proxy.
The endpoint is retrieved, validated against the schema, and authentication/authorization is applied.

The logic for remote endpoints exists in :mod:`dso_api.dynamic_api.remote`.
Its serializers build upon the DSO base classes:

.. graphviz::

    digraph foo {
      DSOSerializer [shape=box]
      DSOModelSerializer [shape=box]
      RemoteSerializer [shape=box]

      DSOSerializer -> RemoteSerializer [dir=back arrowtail=empty]
      DSOSerializer -> DSOModelSerializer [dir=back arrowtail=empty]
    }

|

The serializers have their own factory function;
:func:`~dso_api.dynamic_api.remote.serializers.remote_serializer_factory`.
It uses the Amsterdam Schema data to generate the serializer fields.
