#!/bin/bash
# Run when INITIALIZE_DB parameter is set and migrations are available.
if ! django migrate --check && "$INITIALIZE_DB" = "true";
then
    ./manage.py migrate;
    ./manage.py import_schemas --create-tables --execute;
    schema permissions apply --auto --revoke --create-roles --execute  -a "datasets_dataset:SELECT;scope_openbaar" -a "datasets_datasettable:SELECT;scope_openbaar" -a "datasets_datasetfield:SELECT;scope_openbaar"  -a "datasets_datasetprofile:SELECT;scope_openbaar";

    # Fill tables with mock data if MOCK_DATA is set. Continue on errors.
    if "$MOCK_DATA" = "true";
    then
        ./manage.py create_mock_data --size 20 --exclude None || true;
        ./manage.py relate_mock_data --exclude None || true;
    fi
fi
