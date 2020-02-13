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

To import the latest database from acceptance (replace `<username>` with your
username, assumes your public SSH key is known and you have appropriate level of access.

This command expects the private SSH key to be found in the ~/.ssh folder,
in a file with the name datapunt.key (chmod 600):

    docker-compose exec database update-db.sh  dso_api <username>
    
To import the bag database do the following :

    docker-compose exec bag_v11_database update-db.sh  bag_v11 <username>
