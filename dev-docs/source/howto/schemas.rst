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

    docker compose exec web python manage.py import_schemas --execute [--create-tables] [--create-views]


Using a local version of schema-tools
-------------------------------------

Assuming there is a schema-tools folder right next to the dso-api folder with the
respective checked out repositories, schema-tools is mapped to /tmp/schema-tools
in the web container. This is obviously only needed if you are working with an
unreleased version of schema-tools.

To ensure we use that version of schema-tools, you need to comment it out or remove it
from the requirements. Set your `USER` to `root` in DSO's Dockerfile, and rebuild.
Then run pip install in the container::

    docker compose exec web pip install -e /tmp/schema-tools

.. note:: After installing schema-tools, you will have a lot of __pycache__ folders in your
schema-tools repo. These will need to be cleaned up before building a distribution.

.. note:: When you are not using docker for local development, adjust the commands accordingly.
