Authentication & Authorization
==============================

Authentication
--------------

Authentication happens by checking a JSON Web Token (JWT)
against the public key of a trusted authentication service.
The token carries *scopes*, strings that denote permissions,
which are tested by the
`datapunt-authorization-django <https://github.com/Amsterdam/authorization_django>`_
package.

Authorization Rulesets
----------------------

There are two mechanisms for authorization on schema level:

* The ``auth`` fields in the Amsterdam Schema restrict access to resources.
* The profiles grant permissions, which were restricted by the schema.

Schema Files
~~~~~~~~~~~~

The schema definitions can add an ``auth`` field on various levels:

* The whole dataset
* A single table
* A single field

The absence of an ``auth`` field makes a resource publicly available.

At every level, the ``auth`` field contains a list of *scopes*.
The JWT token of the request must contain *at least one* of these scopes to access the resource.

When there is a scope at both the dataset, table and field level
these should *all* be satisfied to have access to the field.

The scopes of a dataset or table act as mandatory access control.
When those scopes can't be satisfied, the API returns an HTTP 403 Forbidden error.
The fields act a bit different: when the scope of a field is not satisfied,
the field is omitted from the response.

Sometimes it's not possible to remove a field (for example, a geometry field for Mapbox Vector Tiles).
In that case, the endpoints produces a HTTP 403 error to completely deny access.

.. note::
   The schema validation also require an ``authReason`` to be present when ``auth`` is used.
   Government data is expected to be public, unless there is a valid reason for it.
   The ``authReason`` field forces schema authors to consider why data has to be restricted.

Restricting Querying
~~~~~~~~~~~~~~~~~~~~

Besides the ``auth`` field, the ``filterAuth`` attribute allows restricting queries for a field.
This feature can be utilized to make it *harder* to query for a particular field.
Let's say, avoid retrieving all properties owned by a real estate owner.

.. warning::

   If someone manages to dump the whole table, they can off course still query everything within their local copy.
   Hence, it is generally better to restrict access to a field entirely using ``auth`` instead.
   The ``filterAuth`` feature is useful for well-monitored internal data, that is already protected using the ``auth`` field.

Profiles
~~~~~~~~

While the ``auth`` fields define the basic rules for authentication,
*Profiles* provide a more fine-grained approach to authorization.

This addresses the "all or nothing" approach of ``auth`` fields that isn't sufficient in complex cases.
Note however, that profiles are only examined when authorization is already restricted.
So in practice, the ``auth`` scope needs to be defined (e.g. superuser-only),
and then profiles will be analysed to grant permissions for specific use-cases.

Profiles have a name, a set of scopes, and rules that grant additional permissions.
When a request comes in, all profiles are checked against the request's scopes
and only matching profiles are applied.

Here's an example profile in JSON:

.. code-block:: json

    {
        "name": "medewerker",
        "scopes": ["BRP/R"],
        "datasets": {
            "brp": {
                "tables": {
                    "ingeschrevenpersonen": {
                        "permissions": "read",
                        "fields": {
                            "bsn": "read"
                        },
                        "mandatoryFilterSets": [
                            ["bsn", "lastname"],
                            ["postcode", "lastname"]
                        ]
                    }
                }
            }
        }
    }

This profile is only applied when requests have the ``BRP/R`` scope.
If more than one scope is listed, all scopes must be carried for the profile to apply.
By implication, an empty ``scopes`` denotes a profile that always applies.

The ``datasets`` part of the profile lists permissions granted beyond those
that are granted to the scope(s) by the schema.
Permissions already granted by the schema are never taken away.
The permissions granted may be restricted to requests that query particular fields.
With the example profile, requests with scope ``BRP/R``
gain permission to read the field ``bsn`` on the table ``ingeschrevenpersonen``,
provided that the request queries for either ``bsn`` and ``lastname``,
or ``postcode`` and ``lastname`` (or all three fields).

The ``mandatoryFilterSets`` ensures that listings are restricted on a need-to-know basis.
Only when some information can be provided, the API grants access to see the remaining data.
For example, a frontend office employee may only see data of someone when they can already
provide their last name and postal code.

Profiles can also be used to avoid cluttering the main schema with many ``auth`` rules.
Instead, deny full access to the table, and open specific fields via profiles.
For example, a statistician might be allowed to read age and neighbourhood fields to aggregate data,
without ever having access to identifiable data.

Application in DSO-API
----------------------

The dataset and profile files stored in the repository for Amsterdam Schema.
Both are imported into the DSO-API database, and loaded once on startup.

Schematools
~~~~~~~~~~~

The authorization engine is implemented within ``schematools`` as low-level Python objects.
The ``UserScopes`` class provides the main logic, which is accessed within the DSO-API
as ``request.user_scopes.has_..._access()``. Each access function returns a
:class:`~schematools.types.Permission` object with the granted access level.
When no permission is given, the object evaluates to ``False`` in boolean comparisons (e.g. ``if permission``).

The :class:`~schematools.types.Permission` object provides a ``level``, ``sub_value`` and ``transform_function()``
for fine-grained access levels, such as only viewing a field as encoded or only its first three letters.

WFS Logic
~~~~~~~~~

Authorization is also applied to the WFS server; it's one of the reasons
for writing a custom WFS server in the first place.
See the :doc:`wfs` documentation for more details.

.. tip::

    When changing the authorization logic, make sure to test the WFS server endpoint too.
    While most logic is shared, it's important to double-check no additional data is exposed.

.. _create-test-tokens:

Creating Test Tokens
--------------------

When testing datasets with authorization from the command line
you can use the `maketoken` management command, which generates
a test token for the provided scope(s).

This requires DSO-API to be installed in the current virtualenv
(``cd src && pip install -e .``) and the test JWKS to be in the environment.
After setting the latter and getting a token with
::

    cd src/
    export PUB_JWKS="$(cat jwks_test.json)"
    token=$(python manage.py maketoken BRK/RO BRK/RS BRK/RSN)

you can issue a curl command such as
::

    curl http://localhost:8000/v1/haalcentraal/brk/kadastraalonroerendezaken/${id}/ \
        --header "Authorization: Bearer ${token}"
