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

No PostgreSQL server has to be installed, as one is provided via docker-compose.

.. admonition:: Database Reuse Between Projects

    In practice, this project is developed in tandem with an Airflow instance for importing data.
    The Airflow project has instructions to run its two dependent database in Docker containers as well.
    When following the installation instructions of both projects separately, you will end up with two
    instances of the DSO API database in two separate Docker containers.

    Hence, the best way to setup both projects is to follow the Airflow setup instructions and point the
    ``DATABASE_URL`` environment variable for this project to the DSO API
    database container of the Airflow project.

These instructions vary depending on your setup:

Using Docker-Compose
~~~~~~~~~~~~~~~~~~~~

The docker-compose file assumes there is an SSH identity file at ``~/.ssh/datapunt.key``.
So create it::

    cp -i ~/.ssh/id_rsa.key ~/.ssh/datapunt.key

Now we can start the container with the database::

    docker-compose up -d database

.. tip::
    To make sure the environment variables are automatically set
    for the project you're working in, consider using a tool such as
    `direnv <https://github.com/direnv/direnv>`_.

    Add a ``.envrc`` to your project folder, and direnv ensures the proper
    environment variables are loaded when you cd into your project directory.

Using Virtual Machine
~~~~~~~~~~~~~~~~~~~~~

If you are not running Docker locally (eg in Linux) but in a virtual
machine (eg MacOS, FreeBSD, Windows) you might want to adjust the
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

Import schema's::

    ./manage.py import_schemas

Note: This might results in an error
``AttributeError: type object 'kadastraalonroerendezaken_adressen' has no attribute 'koppelingswijze'``
This is because the dataset ``haalcentraalbrk`` is a :ref:`virtual dataset <remote>`.
Some schema features are only supported in local or virtual datasets.
To address the error we need to mark that dataset as a proxy to another URL::

 ./manage.py change_dataset haalcentraalbrk --endpoint-url='http://example.com/{table_id}/'


Run the server
--------------

::

    ./manage.py runserver localhost:8000

The API can now be accessed at: http://localhost:8000
