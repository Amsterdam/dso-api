# DSO API

A new generic API that exposes datasets.
It uses the "Amsterdam Schema" to define the datasets,
and exposes these in a DSO (Digitaal Stelsel Omgevingswet) compatible API.
Part of that means that the API follows the HAL-JSON style.

# Requirements

    Python >= 3.8
    Docker/Docker Compose

# Preparation

    cp -i ~/.ssh/id_rsa.key ~/.ssh/datapunt.key

    python3 -m venv venv
    source venv/bin/activate
    pip install -U wheel pip
    cd src
    make install  # installs src/requirements_dev.txt

If you are not running Docker locally (eg in Linux)
but in a virtual machine (eg MacOS, FreeBSD, Windows)
you might want to adjust the `DATABASE_URL`
to point it to the IP address of the virtual machine instead of simply `localhost`.

Eg, something like:

    export DATABASE_URL=postgres://dataservices:insecure@<vm_ip_addr>:5415/dataservices

Now we can start the container with the database:

    docker-compose up -d database

If you want to use the bag_v11 data also do:

    export BAG_V11_DATABASE_URL=postgres://bag_v11:insecure@<vm_ip_addr>:5434/bag_v11
    docker-compose up -d bag_v11_database

Setting environment variables each and everytime
with potentially different values per project
gets tedious pretty fast.
To solve that you might want to consider using a tool such as `direnv`
and set these variables in a file `.envrc`.
Direnv will ensure the proper environment variables are loaded
when you cd into your project directory.

See: https://github.com/direnv/direnv

# Migrate Django catalog model

    cd src
    python manage.py migrate

# Import schema

    python manage.py import_schemas

This might results in an error
`AttributeError: type object 'kadastraalonroerendezaken_adressen' has no attribute 'koppelingswijze'`
This is because the dataset `hcbrk` is a virtual dataset.
Meaning, that requests for it are proxied to another API;
an API that we apparently cannot access at this moment.
To address the error we need to point requests for that dataset to another valid URL:

    ./manage.py change_dataset hcbrk --endpoint-url=http://google.com

# Run the server

    ./manage.py runserver localhost:8000

The API can now be accessed at: http://localhost:8000

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

# Development details

Extra information on how to develop DSO-API locally can be found in [DEVELOPMENT.md](DEVELOPMENT)

To import the latest database from acceptance (replace `<username>` with your
username, assumes your public SSH key is known and you have appropriate level of access.

This command expects the private SSH key to be found in the ~/.ssh folder,
in a file with the name datapunt.key (chmod 600):

    docker-compose exec database update-db.sh dataservices

To import the bag database do the following :

    docker-compose exec bag_v11_database update-db.sh  bag_v11

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

# Testing OpenAPI schema on localhost

OpenAPI schema can be verified on localhost using following command:

    OPENAPI_HOST=http://localhost:8000 ./.jenkins/openapi_validator/run_validator.sh

Do not forget to replace `OPENAPI_HOST` with address of running DSO api, if it differs from `http://localhost:8000`.
