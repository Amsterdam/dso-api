#!/bin/sh


host=${OPENAPI_HOST:-"https://acc.api.data.amsterdam.nl"}
apk add curl
set -e

echo "$host/v1/openapi.yaml"
curl $host/v1/openapi.yaml --output /tmp/openapi.yaml

spectral lint /tmp/openapi.yaml -s oas3-unused-components-schema -s oas3-server-trailing-slash -s operation-tag-defined -s path-keys-no-trailing-slash -s operation-parameters -s openapi-tags -s no-\$ref-siblings
#     -s oas3-unused-components-schema \  # WARNING: Unused compontents in schema?
#     -s oas3-server-trailing-slash  \ # WARNING: trailing slash present in server spec
#     -s operation-tag-defined \  # WARNING: TAGs not defined
#     -s path-keys-no-trailing-slash \  # WARNING: DSO API ends with trailing slashes
#     -s openapi-tags \  # WARNING: missing OpenAPI tags
#     -s operation-parameters \ # WARNING: A parameter in this operation already exposes the same combination of `name` and `in` values.
#     -s no-$ref-siblings  # ERROR: $ref cannot be placed next to any other properties , Geometry Fields
