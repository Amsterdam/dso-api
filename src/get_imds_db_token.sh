#!/usr/bin/env sh

# This script echoes a shortlived token for connecting to a postgres instance
# It can only be used from a K8S node with the proper identities assigned.


echo $(curl -s\ "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fossrdbms-aad.database.windows.net" -H 'Metadata: true' | python -c 'import json, sys; print(json.loads(sys.stdin.read())["access_token"])')
