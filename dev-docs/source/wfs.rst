WFS Server
==========

The WFS server component is mostly implemented as a separate package: django-gisserver_.
The DSO-API build upon the generic functionality of django-gisserver_ by extending it:

.. graphviz::

   digraph foo {

      wfsview [label="gisserver.views.WFSView" shape=box]
      DatasetWFSView [label="dso_api.dynamic_api.views.DatasetWFSView" shape=box]

      wfsview -> DatasetWFSView  [dir=back arrowtail=empty]
   }

|

.. seealso::
    To learn more about the WFS server component, it's useful to read
    its development documentation at: https://django-gisserver.readthedocs.io/.
    This explains how to define features, override logic and understand its internal design.

    The DSO-API end user documentation also describes how to access the WFS server:
    https://api.data.amsterdam.nl/v1/docs/generic/gis.html


Schema Definitions
------------------

The WFS server is a purely generic WFS server. It has no knowledge of Amsterdam Schema
or the dynamic models. This isn't needed either. To expose data for the WFS server,
the view needs to provide a set of :class:`~gisserver.features.FeatureType` objects.

These objects define what models to read, and which fields to return.
The layer in :mod:`dso_api.dynamic_api.views` translates the dataset definitions
to the proper :class:`~gisserver.features.FeatureType` objects.
By providing the proper feature type, the server constructs the desired response.

Authorization Rules
-------------------

The authorization rules for data are handled in 2 ways:

* The constructed :class:`~gisserver.features.FeatureType` only contains the fields
  that the user may access.
* Our :class:`~dso_api.dynamic_api.views.wfs.AuthenticatedFeatureType` subclass
  implements the :func:`check_permissions` hook that django-gisserver_ provides.
  It checks against the dataset/table-level permissions.

Datasets With Multiple Geometries
---------------------------------

If a table contains multiple geometries, multiple variations fo the feature type
will be included separately in the WFS server. Each variation has a different primary geometry field.

This way, GIS packages can display both geometries on the map.

This can be seen, for example, with "Horeca-exploitatievergunningen" (catering exploitation permits):
a separate layer is made available for the building and the associated terraces.
This way, both geometries can be read. The data of both layers is identical;
only the order of geometry fields has been adjusted.

Expand Logic
------------

The WFS server supports the same expand/embed logic as the REST API endpoints.
This is an "extension" over the standard server logic, that is implemented in two steps:

* The internals of django-gisserver_ support complex objects, that span various relations.
* The DSO-API provides these complex feature definitions when requested.

The WFS ``?embed=...`` and ``?expand=...`` options are processed completely in the DSO-API project.
When such parameter is given, DSO-API constructs a feature type definition
that includes embedded/expanded relations. All the WFS server does, is follow
the provided type definition and behave like any other request.

This also works in QGis. When an WFS endpoint is configured with an ``?embed=...`` query parameter,
QGis will include this query parameter in all server requests - just as if it's part of the "URL".
This way, the WFS requests such as ``GetCapabilities`` or ``GetFeature`` all receive that setting.
Each time, the :class:`~dso_api.dynamic_api.views.DatasetWFSView` constructs the complex feature,
and the WFS server operates based on this definition.

.. seealso::
   The effect of the expand/embed logic is well explained in the end user manual:
   https://api.data.amsterdam.nl/v1/docs/generic/gis.html

.. _django-gisserver: https://github.com/Amsterdam/django-gisserver
