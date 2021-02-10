# Developing DSO-API

Best way to develop DSO-API code locally is by using Dataservices Airflow and it's database for DSO-API.

Combined setup would require setting up [dataservices-airflow](https://github.com/Amsterdam/dataservices-airflow) according to it's [README.md](https://github.com/Amsterdam/dataservices-airflow/blob/master/README.md)

Next you would need to execute one or more DAGs, there are few available with public data:

- openbareverlichting

## Initial setup

Let's start by describing basic directory structure, both `dso-api` and `dataservices-airflow` are expected to be cloned to into same directory for simplicity:

```
~/Projects/
 |-dso-api/
 |-dataservices-airflow/
```

### Airflow setup

Airflow can be started inside docker-compose. This is two-step process:

 - `docker-compose build`
 - `SCHEMA_URL=https://schemas.data.amsterdam.nl/datasets/ docker-compose up`
 
Setup process will require 5 to 10 minutes, depending on hardware.

After few minutes console output will stop showing errors, this is a sign it is okay to create user in separate terminal window:

```
docker-compose exec airflow airflow create_user -r Admin -u admin -e admin@example.com -f admin -l admin -p test
```

### DSO-API

DSO API can be used locally, inside python virtual environment. All commands related to `dso-api` will be assumed to be executed inside virtual environment.

Install `requirements_dev.txt`: `pip install -r src/requirements_dev.txt` (Note: local development packages need to be installed before running this step) 

Next step will require `DATABASE_URL` environment variable to be present that is pointing to DSO database inside `dataservices-airflow` docker-compose setup:

```
export DATABASE_URL="postgresql://dataservices:insecure@localhost:5416/dataservices"
```

And now you're ready to migrate database and import schemas

```
./src/manage.py migrate
./src/manage.py import_schemas 
```

## Importing public data into Airflow Database

In order to import public data we will need to execute `openbareverlichting` DAG in Airflow container. This can be done via interface or via command line.

### Triggering dags via interface

Go to [http://localhost:8080](http://localhost:8080/) and login with username `admin` and password `test`, then open `bouwstroompunten` DAG and click `Trigger DAG` button.
And same for `openbareverlichting` DAG.

### Command line import

Inside `dataservices-airflow` folder run:

```
docker-compose exec airflow bash
airflow test openbareverlichting mkdir 2020
airflow test openbareverlichting download_objects 2020
airflow test openbareverlichting download_objecttypes 2020
airflow test openbareverlichting convert_to_geojson 2020
airflow test openbareverlichting geojson_to_SQL 2020
airflow test openbareverlichting create_table 2020
airflow test openbareverlichting rename_columns 2020
airflow test openbareverlichting multi_check 2020
airflow test openbareverlichting rename_table 2020
```


# Daily use

You will need to run `docker-compose up -d dso_database` in `dataservices-airflow` and make sure that `DATABASE_URL` environment variable is present (hint: use direnv):

```
export DATABASE_URL="postgresql://dataservices:insecure@localhost:5416/dataservices"
```

After that `dso-api` can be started locally by running `./src/manage.py runserver`


Happy Hacking!
