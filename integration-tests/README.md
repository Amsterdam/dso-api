# DSO API - Integration Tests

These integration tests have been set up to make sure all environment variables are tested to ensure a correct
deployment of the DSO API.

# Installation

Requirements:

* Python >= 3.14
* Recommended: Docker/Docker Compose (or uv for local installs)

## DSO API

The easiest way to run these integration tests is by using Docker Compose. This will also start the DSO API.

To be able to run the tests you will need a valid token to be able to make the requests. The easiest way is to set up
direnv with an `.envrc` file or export a token from the command line:

```shell
export TOKEN="$(docker compose run web python get-token.py FP/MDW)"
```

After having a valid token in your environment you'll be able to start the tests using:

```shell
docker compose run tests
```

## Using Local Python

Make sure you have the DSO API an environment variable `DATAPUNT_API_URL`
set to the URL of the DSO API. You can use uv to start the services:

```shell
docker compose up -d -f ../docker-compose.yml
export DATAPUNT_API_URL=http://localhost:8090
```

```shell
uv sync
uv run dso-test
```
