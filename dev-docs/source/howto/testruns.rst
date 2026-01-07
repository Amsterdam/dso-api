.. highlight:: console

Running Tests
=============

Unit Tests and Coverage Report
------------------------------
You can run the unit tests with:

    docker compose exec -u root -T web pytest -v --ds=tests.settings

.. note::
    the `-u root` flag is necessary because the ``dsoapi`` user does not have write
    access and coverage depends on writing some files.

This will read in the settings in ``pyproject.toml``, which automatically adds a
coverage report.

To run the tests without creating a coverage report use the ``--no-cov`` flag, the
``-u root`` flag can then be omitted.

To create a different type of output, use the ``--cov-report`` flag, for example:

    docker compose exec -u root -T web pytest -v --ds=tests.settings --cov-report=html

We strongly suggest you create useful aliases for these commands.

The test coverage is checked in the test workflow on Github, see ``.github/workflows/test.yaml``.

Running Tests Outside of Docker
===============================

Unit Tests
----------

The unit tests use the pytest framework.
This can be run using::

    cd src
    make test

.. tip::
    On test failures, run ``make retest``.

Coverage
--------

Coverage can be tested using::

    make coverage

To analyse the results, see which lines are touched::

    coverage html
    open htmlcov/index.html
