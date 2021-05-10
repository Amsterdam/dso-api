.. highlight:: console

Schema Development
==================

Using local versions of schemas
-------------------------------

To import a custom schema for testing/development, use the command::

    ./manage.py import_schemas schemafile.json

For more complicated cases, there is a nginx server ``schemas`` in
``docker-compose.yml`` that acts as a replacement for
``schemas.data.amsterdam.nl``.

It reads its config from ``schemas/conf/default.conf``
and datasets from ``schemas/data/datasets``.
It can be started with::

    docker-compose up -d schemas

Then point to this server as the schema server and import schemas from it::

    export SCHEMA_URL=http://localhost:8080/datasets
    ./manage.py import_schemas
