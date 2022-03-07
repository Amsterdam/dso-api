.. highlight:: console

Installation
============

These instructions will get the DSO API up and running locally with its
database running in a Docker container with an empty database.

Requirements
------------

* Python >= 3.9
* Recommended: Docker / docker-compose

Preparation
-----------

For local development, create a virtualenv::

    python3 -m venv venv
    source venv/bin/activate

Install the tools::

    pip install -U wheel pip
    cd src
    make install  # installs src/requirements_dev.txt

.. tip:
    If you're running FreeBSD, see the :doc:`freebsd`.

Database Setup
--------------

DSO-API talks to a PostgreSQL instance that contains its data.
Normally, you should use the one from the dataservices-airflow project.
If you don't already have it running, do::

    git clone https://github.com/Amsterdam/dataservices-airflow
    cd dataservices-airflow
    docker-compose up dso_database

Then point to that PostgreSQL in the environment::

    DATABASE_URL=postgres://dataservices:insecure@localhost:5416/dataservices

.. tip::
    To make sure the environment variables are automatically set
    for the project you're working in, consider using a tool such as
    `direnv <https://github.com/direnv/direnv>`_.

    Add a ``.envrc`` to your project folder, and direnv ensures the proper
    environment variables are loaded when you cd into your project directory.

Using a Virtual Machine
~~~~~~~~~~~~~~~~~~~~~~~

If you are not running Docker locally (as on Linux) but in a virtual
machine (as needed on MacOS, FreeBSD, Windows) you might want to adjust the
``DATABASE_URL`` to point it to the IP address of the virtual machine
instead of simply ``localhost``.

Eg, something like::

    export DATABASE_URL=postgres://dataservices:insecure@<vm_ip_addr>:5415/dataservices

Using a local PostgreSQL server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A local PostgreSQL server can be used. It needs to have PostGIS installed as well.
Then the ``DATABASE_URL`` can be pointed at it::

    export DATABASE_URL=postgres://dataservices:insecure@localhost/dataservices

.. warning::
    This setup may become complicated, even work software like homebrew.
    A ``brew install postgis`` only installs PostGIS in the default PostgreSQL instance.
    This won't work if you're running a PostgreSQL server through ``brew install postgresql@<version>``,
    unless you're willing to dive deep onto PostGIS internals and symlink the required files.


Completing the Setup
--------------------

Create database tables::

    ./manage.py migrate

Import schemas::

    ./manage.py import_schemas

Note: This might results in an error
``AttributeError: type object 'kadastraalonroerendezaken_adressen' has no attribute 'koppelingswijze'``
This is because some datasets are :ref:`virtual datasets <remote>`.
Some schema features are only supported in local or virtual datasets.
To address the error we need to mark that dataset as a proxy to another URL::

 ./manage.py change_dataset haalcentraalbag --endpoint-url='http://example.com/{table_id}/'
 ./manage.py change_dataset haalcentraalbrk --endpoint-url='http://example.com/{table_id}/'


Run the server
--------------

The server needs a JSON Web Key Set (JWKS) to perform authorization,
even when authorized endpoints aren't used; it refuses to start without one.
For testing and development, use the one in ``jwks_test.json``:

::
    export PUB_JWKS="$(cat jwks_test.json)"

Then start DSO-API:

::

    ./manage.py runserver localhost:8000

The API can now be accessed at: http://localhost:8000.
