#!/bin/env sh

echo $(curl -s "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fossrdbms-aad.database.windows.ne" -H Metadata:true | python -c 'import json, sys; print(json.loads(sys.stdin.read())["access_token"])')
