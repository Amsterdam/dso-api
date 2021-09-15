.. highlight:: console

Running Tests
=============

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
