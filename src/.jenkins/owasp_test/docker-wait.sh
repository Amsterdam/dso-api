#!/usr/bin/env bash

set -u   # crash on missing env variables
set -e   # stop on any error

# wait for postgres
while ! nc -z owasp 8090
do
	echo "Waiting for ZAP (zeds attack proxy)..."
	sleep 2
done
