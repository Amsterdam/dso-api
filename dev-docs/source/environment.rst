Environment Variables
=====================

The following environment variables can be configured to change the application behavior:

Disabling Automatic Model Creation
----------------------------------

.. _INITIALIZE_DYNAMIC_VIEWSETS:

In case the dynamic models+endpoints shouldn't be configured, pass ``INITIALIZE_DYNAMIC_VIEWSETS=0``.
This is enabled by default for ``manage.py showmigrations`` and ``manage.py migrate``:

.. code-block:: bash

    INITIALIZE_DYNAMIC_VIEWSETS = 0

Hosting Specific Datasets
-------------------------

.. _DATASETS_LIST:
.. _DATASETS_EXCLUDE:

By default, all datasets are hosted by the application.
When a custom instance is deployed for a particular dataset (e.g. the BRP),
this instance can host only a subset using:

.. code-block:: bash

    DATASETS_LISTS = ...
    DATASETS_EXCLUDE = ...

.. warning::

    Relations and expanding logic are also affected when certain datasets are not loaded.

Dataset Schema Locations
------------------------

.. _SCHEMA_URL:
.. _PROFILES_URL:

The following variables define the locations for datasets:

.. code-block:: bash

    SCHEMA_URL = https://schemas.data.amsterdam.nl/datasets/    # Where schema's are loaded.
    PROFILES_URL = https://schemas.data.amsterdam.nl/profiles/  # Where auth-profiles are loaded.
    SCHEMA_DEFS_URL = https://schemas.data.amsterdam.nl/schema  # Prefix for meta schemas


Remote API Endpoints
--------------------

.. code-block:: bash

    # Haalcentraal
    HAAL_CENTRAAL_API_KEY = ...
    HC_KEYFILE = ...
    HC_CERTFILE = ...


Remaining Configuration
-----------------------

The following environment variables are also available,
but not further explained as these are typical settings for all Docker containers:

.. code-block:: bash

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
