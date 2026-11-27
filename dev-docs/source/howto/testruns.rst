.. highlight:: console

Running Tests
=============

Unit Tests and Coverage Report
------------------------------
You can run the unit tests with:

    docker compose exec -u root -T web uv run pytest -v --ds=tests.settings

.. note::
    the `-u root` flag is necessary because the ``dsoapi`` user does not have write
    access and coverage depends on writing some files.

This will read in the settings in ``pyproject.toml``, which automatically adds a
coverage report.
Coverage settings, exclusions, and the 91% threshold are all defined in the
root ``pyproject.toml``.

To run the tests without creating a coverage report use the ``--no-cov`` flag, the
``-u root`` flag can then be omitted.

To create a different type of output, use the ``--cov-report`` flag, for example:

    docker compose exec -u root -T web uv run --no-sync pytest -v --ds=tests.settings --cov-report=html

We strongly suggest you create useful aliases for these commands.

The test coverage is checked in the test workflow on Github, see ``.github/workflows/test.yaml``.

OpenAPI Validation
------------------

The ``test-openapi-spec`` workflow loads the schemas in ``schemas/data`` and
validates the generated BAG OpenAPI document with Spectral.
It supplies ``src/jwks_test.json`` through ``PUB_JWKS`` so authentication can
initialize without production keys.
Referenced table fixtures must define a status, matching their dataset version.
``docker-compose.test-openapi-spec.yml`` supplies a test-only OAuth authorization
URL so the document can be validated without configuring an identity provider.

Running Tests Outside of Docker
===============================

Unit Tests
----------

The unit tests use the pytest framework.
This can be run using::

    make test

.. tip::
    On test failures, run ``make retest``.

Coverage
--------

Coverage can be tested using::

    make coverage

To analyse the results, see which lines are touched::

    uv run coverage html
    open htmlcov/index.html
