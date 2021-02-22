.. vim:noswapfile:nobackup:nowritebackup:
.. highlight:: console

# DSO API

A new generic API that exposes datasets.
It uses the "Amsterdam Schema" to define the datasets,
and exposes these in a DSO (Digitaal Stelsel Omgevingswet) compatible API.
Part of that means that the API follows the HAL-JSON style.

These instructions will get the DSO API up and running locally
with its database running in a Docker container.
If that's what you are after, 
by all means go ahead
However, in practice the DSO API is developed in tandem with Airflow.
The Airflow project has instructions to run its two dependent database in Docker containers as well.
One of these dependent databases is the DSO API database.
Should you follow the installation instructions of both projects separately,
you will end up with two instances of the DSO API database in two separate Docker containers.
That is likely not what you intended. 
Hence the best way to setup both projects
is to follow the Airflow setup instructions
and point the ``DATABASE_URL`` environment variable for this project 
to the DSO API database container of the Airflow project.

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
    
Should the above fail with errors related to ``orjson`` and/or ``maturin``
and you are running FreeBSD,
then please see the 
[FreeBSD Installation Instructions](#FreeBSD-Installation-Instructions)

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

Extra information on how to develop DSO-API locally can be found in [DEVELOPMENT](DEVELOPMENT.md)

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
    
# FreeBSD Installation Instructions

Installing the DSO API under FreeBSD should be largely similar to installing it under Linux or MacOS.
However, some extra work will be required to build packages that rely on code written in other languages
and for which the package authors did not provide FreeBSD specific wheels.

## Maturin

``Maturin`` by default, 
and not easily overideable,
strips all symbols from the binaries that the Rust compiler produces.
For some reason this confuses the LLVM linker.
The easiest solution is to install GCC9 
and use its linker during ``maturin`` build process:

    % sudo pkg install gcc9
    % CARGO_BUILD_RUSTFLAGS='-C linker=/usr/local/bin/gcc9' pip install maturin

## Orjson

``Orjson`,
depending on its version,
requires a different nightly build of the Rust compiler.
At the time of writing,
the version of ``orjson`` used,
version 3.4.6,
requires the rust nightly compiler from 2021-01-02.
Hence before attempting to run:

    % pip install orjson==3.4.6

or:

    % make -C src install

one needs to install that specific nightly version of the rust compiler by:

   % curl https://sh.rustup.rs -sSf | sh -s -- --default-toolchain nightly-2021-01-02 --profile minimal -y

# Testing OpenAPI schema on localhost

OpenAPI schema can be verified on localhost using following command:

    OPENAPI_HOST=http://localhost:8000 ./.jenkins/openapi_validator/run_validator.sh

Do not forget to replace `OPENAPI_HOST` with address of running DSO api, if it differs from `http://localhost:8000`.


# Limiting number of Datasets available via API

In some cases it might be required to isolate datasets from others on infrastructure level, 
for example sensitive information should not be published via Public APIs, but public information should be available in private API.

This can be achieved by using `DATASETS_LIST` and `DATASETS_EXCLUDE` environment variables.
Both variables accept comma separated list of dataset ids e.g. `bommen,gebieden,meldingen` etc.

* To expose only a subset of the datasets, use `DATASETS_LIST`.
* To expose all datasets with some exceptions, use `DATASETS_EXCLUDE`.

Both `DATASETS_LIST` and `DATASETS_EXCLUDE` variables should be used with great care, 
as any relation to dataset outside of those loaded into memory will break API.
