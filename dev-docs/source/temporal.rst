Temporal Datasets
=================

Some datasets contain historical data. This allows you to navigate through previous versions of the same object.
By default, the API only returns the current version of these objects.

Navigating to other occurrences/versions is called "time travel in the
`DSO standard <https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/>`_.
Hence we speak of "temporal datasets".

.. seealso::
   The general description of temporal tables for end-users (in dutch):
   https://api.data.amsterdam.nl/v1/docs/generic/rest/temporal.html

Requesting Versions
-------------------

When a table is requested, the temporal data of *one specific moment* is returned.
Both the "listing" and "detail" view also support requesting different versions.
End-users can use the following functionality:

* By default, see the most recent version, e.g. `Riekerpolder <https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/>`_
* Using `?volgnummer=.. <https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?volgnummer=1>`_ to get a specific version.
* Using `?geldigOp=yyyy-mm-dd <https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?geldigOp=2010-04-30>`_ to find the objects in a specific time frame.

All relations, and embedded objects also follow this query;
so it allows to see the state like it was at a specific moment in time.

Within the results, the temporal query is also repeated in URLs of  the ``_links`` section.
This makes sure all references point to the correct linked versions.

Search Axis
~~~~~~~~~~~

There are several axes on which to query the various "occurrences" of an object.
These dimensions can be defined in the schema ``temporal.dimensions`` attribute:

.. list-table::
   :header-rows: 1

   * - Dimension (axis)
     - DSO Parameter Name
     - Description
   * - Valid on
     - ``?geldigOp=...``
     - When something is active.
   * - Available on
     - ``?beschikbaarOp=...``
     - System entry date.
   * - In effect on
     - ``?inWerkingOp=...``
     - Rules that take effect earlier/later.

Database Layout
---------------

Temporal records use a composite key, typically made using following fields:

* "identificatie"
* "volgnummer"

These names are arbitrary however. The dataset can define which fields are used in a temporal relation.
The first field is treated as the group-identifier, the second field to distinguish between
individual records in the group. For example, all records of a particular neighbourhood
have the same "identifier" but a different "volgnummer" and date.

Other tables can refer to a temporal record in two ways:

* A reference to the first grouping identifier only (called a "loose relation" in the code).
* A reference to both a specific version/occurrence of the object (a composite foreign key).

Relationships
~~~~~~~~~~~~~

Relationships may also contain temporality.
For example, consider a neighborhood that is linked to a new area.
Both objects are unchanged, but the relationship object is versioned instead.
Versioned relationships require a separate table, as the start/end-date should be stored there as well.

Django Notes
~~~~~~~~~~~~

While having a composite primary key is possible database-wise, Django does not support this.
Hence a unique "id" field is also needed in the tables
(typically a varchar that concatenates :samp:`"{identificatie}.{volgnummer}"`)
because Django doesn't support composite keys.

Most of the time through, a query happens on the group identifier,
combined with a where-condition that limits the results to one record.

For temporal tables, the functions ``filter_temporal_slice()`` and ``filter_temporal_m2m_slice()``
are consistently applied to make sure only records from the selected time period are returned.
This also affects loose relations; when a table join happens on the first identifier part alone,
the temporal slicing makes sure only one record is returned.

Amsterdam Schema Representations
--------------------------------

A temporal dataset is created by defining a **temporal** section
and using a compound key as **identifier**.
The field names should also exist in the table:

.. code-block:: json

    {
      "id": "panden",
      "type": "table",
      "temporal": {
        "identifier": "volgnummer",
        "dimensions": {
          "geldigOp": ["beginGeldigheid", "eindGeldigheid"]
        }
      },
      "schema": {
        "type": "object",
        "identifier": ["identificatie", "volgnummer"],
        "properties": {
          "identificatie": {"type": "string"},
          "volgnummer": {"type": "integer"},
          "beginGeldigheid": {"type": "string", "format": "date-time"},
          "eindGeldigheid": {"type": "string", "format": "date-time"},
        }
      }
    }

The fields (identificatie, volgnummer, beginGeldigheid, eindGeldigheid) are defined
as standard table fields, and get additional meaning by being mentioned
in the ``identifier`` and ``temporal`` sections.

Foreign keys to temporal objects are defined by creating a **relation** with **type=object**:

.. code-block:: json

    "ligtInBouwblok": {
      "type": "object",
      "relation": "gebieden:bouwblokken",
      "properties": {
        "identificatie": {"type": "string"},
        "volgnummer": {"type": "integer"}
      }
    }

If the "volgnummer" field is omitted, the relation only uses the first grouping field,
and becomes a "loose relation".

To make the relation versioned, additional date fields can be added to the relation object:

.. code-block:: json

    "ligtInWoonplaats": {
      "type": "object",
      "relation": "bag:woonplaatsen",
      "properties": {
        "identificatie": {"type": "string"},
        "volgnummer": {"type": "integer"},
        "beginGeldigheid": {"type": "string", "format": "date-time"},
        "eindGeldigheid": {"type": "string", "format": "date-time"}
      }
    }
