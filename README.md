# DSO API

A new generic API that exposes datasets.
It uses the "Amsterdam Schema" to define the datasets,
and exposes these in a DSO (Digitaal Stelsel Omgevingswet) compatible API.
Part of that means that the API follows the HAL-JSON style.

# Requirements

    Python >= 3.8

# Preparation

    cp -i ~/.ssh/id_rsa.key ~/.ssh/datapunt.key

    python3 -m venv venv
    source venv/bin/activate
    cd src
    make install  # installs src/requirements_dev.txt

    docker-compose up -d database

If you want to use the bag_v11 data also do :

    docker-compose up -d bag_v11_database

# Migrate Django catalog model

    cd src
    python manage.py migrate

# Import schema

    python manage.py import_schemas

# Run the server

    docker-compose up

The server can be reached locally at:

    http://localhost:8000


# Managing requirements.txt

This project uses [pip-tools](https://pypi.org/project/pip-tools/)
and [pur](https://pypi.org/project/pur/) to manage the `requirements.txt` file.

To add a Python dependency to the project:

* Add the dependency to `requirements.in`
* Run `make requirements`

To upgrade the project, run:

    make upgrade
    make install
    make test

Or in a single call: `make upgrade install test`

Django will only be upgraded with patch-level versions.
To change from e.g. Django 3.0 to 3.1, update the version in `requirements.in` yourself.


# Importing the latest backup

To import the latest database from acceptance you can login with your named account on the acceptance database and make an export of the desired objects and import them in your local database.


# Using a local version for schema import

For testing it is convenient to have local server for schema importing.

In the docker-compose there is a nginx server **schemas** that will serve this purpose.
It will read the config from **_schemas/conf/default.conf_** and datasets from **_schemas/data/datasets_**

It can be started with :

    docker-compose up -d schemas

Point to this server as schema server with :

    export SCHEMA_URL=http://localhost:8080/datasets

Then it will import the schemafiles in **_schemas/data/datasets_** with :

    python manage.py import_schemas

