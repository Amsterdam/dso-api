#!/usr/bin/env bash

set -u # crash on missing env
set -e # stop on any error

export COMPOSE_PROJECT_NAME=dso_api_$(git rev-parse --short HEAD)

echo "Waiting for db"
source .jenkins/docker-wait.sh
source .jenkins/docker-migrate.sh

echo "Running style checks"
flake8 --config=.flake8 ./dso_api

# echo "Running unit tests"
DJANGO_DEBUG=false pytest --nomigrations -vs --ds=tests.settings --show-capture=no
