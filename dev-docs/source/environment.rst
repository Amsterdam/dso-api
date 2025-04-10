.. highlight:: console

Environment Variables
=====================

The following environment variables can be configured to change the application behavior:

Disabling Automatic Model Creation
----------------------------------

.. _INITIALIZE_DYNAMIC_VIEWSETS:

In case the dynamic models+endpoints shouldn't be configured, pass ``INITIALIZE_DYNAMIC_VIEWSETS=0``.
This is enabled by default for ``manage.py showmigrations`` and ``manage.py migrate``::

    INITIALIZE_DYNAMIC_VIEWSETS = 0

Hosting Specific Datasets
-------------------------

.. _DATASETS_LIST:
.. _DATASETS_EXCLUDE:

By default, all datasets are hosted by the application.
When a custom instance is deployed for a particular dataset (e.g. the BRP),
this instance can host only a subset using::

    DATASETS_LIST = ...
    DATASETS_EXCLUDE = ...

To expose only a subset of the datasets, use ``DATASETS_LIST``.
To expose all datasets with some exceptions, use ``DATASETS_EXCLUDE``.

Both entries accept a comma separated list, e.g. ``DATASETS_LIST=bommen,gebieden,meldingen``.

.. warning::

    Relations and expanding logic are also affected when certain datasets are not loaded.

Logging
-------

By default, everything from the ``INFO`` log level and up are logged.
This can be changed using::

    DJANGO_LOG_LEVEL = ...
    DSO_API_LOG_LEVEL = ...
    DSO_API_AUDIT_LOG_LEVEL = ...

For some endpoints, when error messages are generated, those message
are containing too much confidential information (like BSN numbers) to end up in the Sentry logs.

So, it is possible to ignore certain endpoints based on the `path` part of the url
using the environment variable `SENTRY_BLOCKED_PATHS`. This environment variable
should contain a comma-separated list of strings that will flag the endpoint for
not logging to Sentry when one of the defined strings in this environment variable
is part of the url.


Dataset Schema Locations
------------------------

.. _SCHEMA_URL:
.. _PROFILES_URL:

The following variables define the locations for datasets::

    SCHEMA_URL = https://schemas.data.amsterdam.nl/datasets/    # Where schema's are loaded.
    PROFILES_URL = https://schemas.data.amsterdam.nl/profiles/  # Where auth-profiles are loaded.
    SCHEMA_DEFS_URL = https://schemas.data.amsterdam.nl/schema  # Prefix for meta schemas


Cloud environment
-----------------

Depending on where the DSO API is being run, it might need to perform additional configuration.

We support Azure logging and tracing when the ``CLOUD_ENV=azure`` setting is used.
When running in Azure two additional environment variables need to be
specified:

-  ``AZURE_APPI_CONNECTION_STRING``

This defines where Azure Application Insights
(`appi <https://docs.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations>`_)
information should be sent to.

Optionally Audit logs can be sent to separate Azure Application Insights instance:

-  ``AZURE_APPI_AUDIT_CONNECTION_STRING``

This value defaults to ``AZURE_APPI_CONNECTION_STRING`` if not defined.

Database configuration is fetched from environment variables while ``PGPASSWORD`` will be fetched from secret named ``mdbdataservices-read`` in KeyVault:

- ``PGDATABASE``

Database Name.

- ``PGUSER``

Database User Name.

- ``PGHOST``

Database Host Name.

- ``PGPORT``

Database Host Port.

If ``CLOUD_ENV`` is not set or not starting with ``azure`` is assumes its value to be a regular hosting provider.


Querying Application Insights
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Regular logs can be queries in related Application Insights instance via `logs` screen with following query:

```
traces
| extend stack = parse_json(message)
| where stack.level == "DEBUG"
| project stack.level, stack.message, timestamp
```

Note: `stack` is an object and contains a bit more information than just `level` and `message` (add: `stack` to `project ` line to see more)

Exceptions are available via following query:

```
exceptions
| extend x = split(outerMessage, "Traceback")
| extend error_log = parse_json(tostring(x[0]))
| extend path = split(error_log.message, "Error: ")[1]
| project timestamp, path, error_log.level, x[1], x[2], x[3], x[4]
```

Where columns `x[1]`, `x[2]`, `x[3]` and `x[4]` can contain python stack trace parts.


Audit logs are queries in separate Application Insights instance with:

```
traces
| extend msg = parse_json(message)
| project timestamp, msg.level, msg.message
```

Remaining Configuration
-----------------------

The following environment variables are also available,
but not further explained as these are typical settings for all Docker containers::

    # Hosting config
    DATAPUNT_API_URL = https://api.data.amsterdam.nl/           # Public endpoint
    ALLOWED_HOSTS = *

    # Flags & security
    DJANGO_DEBUG = 1
    SECRET_KEY = secret
    SESSION_COOKIE_SECURE=1   # default: not DEBUG
    CSRF_COOKIE_SECURE=1      # default: not DEBUG

    # Services
    DATABASE_URL = postgres://user:pass@host/dbname
    EMAIL_URL = smtp://
    SENTRY_DSN = https://....
    CACHE_URL = locmemcache://

    # Amsterdam oauth settings
    PUB_JWKS = ...
    KEYCLOAK_JWKS_URL = ...
