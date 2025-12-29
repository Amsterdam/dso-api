Subresources
============

Some resources only make sense within the context of another resource.
For such resources, nested urls have been implemented.

Implementation
--------------

The owner of the dataset adds a ``subresources`` property to the table in
the schema, linking a subresource (child) table name to a field on that table
linking to the current (parent) table - i.e. for one-to-many relations.

In schema-tools such subresources are then added to the DatasetTableSchema.
Validation is implemented to ensure that the fields exist on the table and that
the table is within the same dataset.

In the DSO-API, when creating the routes, we iterate over the subresources and
recursively create routes for them (i.e. sub-subresources are nested under the
subresource).

To achieve this, we have some mixins in the dso_api.dynamic_api.nesting
module, a NestedRouterMixin and a NestedViewsetMixin. The NestedRouterMixin
ensures that the router can register routes under other routes. For such nested
routes, it attaches parent lookup kwargs that are read in the NestedViewsetMixin
to filter the queryset.

In the dso_api.dynamic_api.routers module, the logic for adding these nested
routes is in ``DynamicRouter._build_nested_viewsets``.


Amsterdam Schema Representation
-------------------------------

A subresource is defined in the schema as follows on the parent table:

.. code-block:: json

    {
        "id": "stadsdelen",
        "type": "table",
        "subresources": {
            "gebieden:wijken": "ligtInStadsdeel"
        },
        "schema": {
            "type": "object",
            "identifier": ["id"],
            "properties": {
                "id": {"type": "string"},
                "naam": {"type": "string"}
            }
        }
    }

The ``subresources`` field maps table names, prefixed by their dataset, to field names
that link the subresource to the parent resource.

For completeness, this is how the subresource looks, it is identical to how a normal
1N relation field is defined.

.. code-block:: json
    {
        "id": "wijken",
        "type": "table",
        "schema": {
            "type": "object",
            "identifier": ["identificatie", "volgnummer"],
            "properties": {
                "id": {"type": "string"},
                "naam": {"type": "string"},
                "ligtInStadsdeel": {
                    "type": "string",
                    "relation": "gebieden:stadsdelen",
                    "title": "Wijk ligt in stadsdeel",
                    "description": "Het stadsdeel waar de wijk in ligt"
                }
            }
        }
    }

Note
~~~~

Subresources are also available at top-level to ensure backwards compatibility.
