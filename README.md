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

# Migrate Django catalog model

    cd src
    python manage.py migrate

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
