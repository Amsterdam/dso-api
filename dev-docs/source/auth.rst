Authentication & Authorization
==============================

Authentication
--------------

Authentication happens by checking a JSON Web Token (JWT)
against the public key of a trusted authentication service.
These scopes are tested by the
`datapunt-authorization-django <https://github.com/Amsterdam/authorization_django>`_
package.

Authorization
-------------

The schema definitions can add an ``auth`` field on various levels:

* The whole dataset
* A single table
* A single field

At every level, the ``auth`` field contains a string that is called a *scope*.
A request's JWT must contain this scope in its ``scopes`` claim
(see the ``authorization_django`` source code for details)
to meet an ``auth`` field's requirements.
The absence of an ``auth`` field marks a publicly available resource.

The presence of ``auth`` fields on multiple levels
means that all listed scopes must be carried in the JWT.
So, if the dataset has ``"auth": "FOO/BAR"`` and a field has ``"auth": "FOO/BAZ``,
then access to the field is only available
with a token that carries the ``FOO/BAR`` and ``FOO/BAZ`` scopes.

The effect of an ``auth`` on a dataset or table is that attempts to access it
result in an HTTP 403 Forbidden error.
The effect on a field is that the field is omitted when from the response
when the table is queried.
The Mapbox Vector Tiles (MVT) endpoint is an exception to this rule:
since the MVT format requires a geometry field,
the endpoint cannot produce valid MVT when access to the geometry field is prohibited
and gives 403 in this case.

Profiles
--------

The ``auth`` fields define the basic rules for authentication.
Unfortunately, this is a "all or nothing" approach that isn't sufficient in complex cases.
To overcome this problem, "authentication profiles" were introduced.
The file format provides various options, such as:

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
                            "bsn": "encoded"
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

A user may have multiple profiles.
Each profile gives the user additional rights to view a particular resource.

The ``mandatoryFilterSets`` setting ensures that a listing can only be requested
when a certain set of filters is are given. For example, a frontend office employee
may only access data of someone when they can provide their last name and postal code.

Another case for profiles would be a statistician, that may only read the age and neighbourhood
fields to aggregate data, without ever having access to identifiable data.
Encoding such feature into the schema file amongst other rules would produce
very complex ``auth`` fields, while the profile file gives a
fitting definition of such role and permissions.


WFS Logic
---------

Authorization is also applied to the WFS server; it's one of the reasons
for writing a custom WFS server in the first place.
See the :doc:`wfs` documentation for more details.

.. tip::

    When changing the authorization logic, make sure to test the WFS server endpoint too.
    While most logic is shared, it's important to double-check no additional data is exposed.


Testing
-------

When testing datasets with authorization from the command line,
you can generate a JWT with the following script:

.. code-block:: python

    import json
    import sys
    import time
    
    from django.conf import settings
    from jwcrypto.jwk import JWK
    from jwcrypto.jwt import JWT
    
    
    key = JWK(**json.loads(settings.JWKS_TEST_KEY)["keys"][0])
    
    # Validity period, in seconds.
    valid = 1800
    
    scopes = sys.argv[1:]
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + valid,
        "scopes": scopes,
        "sub": "test@tester.nl",
    }
    token = JWT(header={"alg": "ES256", "kid": key.key_id}, claims=claims)
    
    token.make_signed_token(key)
    print(token.serialize())

This requires DSO-API to be installed in the current virtualenv
(``cd src && pip install -e .``).
If the script called is ``maketoken.py``,
you can now issue a curl command such as
::

    curl http://localhost:8000/v1/hcbrk/kadastraalonroerendezaken/${id}/ \
        --header "Authorization: Bearer $(python maketoken.py BRK/RSN)"
