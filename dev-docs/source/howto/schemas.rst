.. highlight:: console

Schema Development
==================

While developing a new metaschema, or a new version of schema-tools, it is often
useful to port these into DSO-API, to ensure everything is still working correctly


Using local versions of schemas
-------------------------------

Assuming the amsterdam-schema repo is checked out in a folder with the same name
next to the dso-api folder, the datasets, publishers, scopes, and profiles folders
are mapped as volumes in the container's /tmp folder.

To ensure that these are used when importing schemas, set a ``SCHEMA_URL`` env
variable to `/tmp/datasets`.

In the running web container you can then run the import::

    docker compose exec web uv run src/manage.py import_schemas --execute [--create-tables] [--create-views]


Using a local version of schema-tools
-------------------------------------

Assuming there is a schema-tools folder right next to the dso-api folder with the
respective checked out repositories, schema-tools is mapped to /tmp/schema-tools
in the web container. This is obviously only needed if you are working with an
unreleased version of schema-tools.

Register the local checkout as an editable uv dependency::

    docker compose exec -u root web uv add --editable /tmp/schema-tools

uv updates the container's ``pyproject.toml`` and ``uv.lock`` and installs the
local checkout. Subsequent ``uv run`` commands keep using this local source.
Rebuild and recreate the container to restore the repository's locked dependencies.

.. note:: After installing schema-tools, you will have a lot of __pycache__ folders in your
schema-tools repo. These will need to be cleaned up before building a distribution.

.. note:: When you are not using docker for local development, adjust the commands accordingly.
