#!/usr/bin/env bash

set -u   # crash on missing env variables
set -e   # stop on any error

echo "Migrating db"
export DATABASE_URL=$DATABASE_URL_WRITE
yes yes | INITIALIZE_DYNAMIC_VIEWSETS=0 python ./manage.py migrate --noinput
