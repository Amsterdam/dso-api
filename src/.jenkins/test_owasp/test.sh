#!/usr/bin/env bash

set -u # crash on missing env
set -e # stop on any error

echo "Waiting for OWASP"
source .jenkins/test_owasp/docker-wait.sh

# echo "Running OWASP tests"
DJANGO_DEBUG=false pytest .jenkins/test_owasp/test_owasp_api.py
