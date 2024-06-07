#!/bin/bash
# Run when INITIALIZE_DB parameter is set and migrations are available.
if ! django migrate --check && "$INITIALIZE_DB" = "true";  
then
    ./manage.py migrate;
    ./manage.py import_schemas --create-tables;
    schema permissions apply --auto --revoke --create-roles --execute  -a "datasets_dataset:SELECT;scope_openbaar" -a "datasets_datasettable:SELECT;scope_openbaar" -a "datasets_datasetfield:SELECT;scope_openbaar"  -a "datasets_datasetprofile:SELECT;scope_openbaar";
fi