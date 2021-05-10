.. highlight:: console

Managing requirements.txt
=========================

This project uses `pip-tools <https://pypi.org/project/pip-tools/>`__
and `pur <https://pypi.org/project/pur/>`__ to manage the
``requirements.txt`` file.

To add a Python dependency to the project:

-  Add the dependency to ``requirements.in``
-  Run ``make requirements``

To upgrade the project, run::

    make upgrade
    make install
    make test

Or in a single call: ``make upgrade install test``

Django will only be upgraded with patch-level versions.
To change from e.g. Django 3.0 to 3.1, update the version in ``requirements.in`` yourself.

.. note::
    Typically, code changes are required when upgrading to newer Django versions.
    For example, some feature could be deprecated by the newer Django version.
    For this reason, third-party modules also need to be upgraded and might add more
    breaking changes that need to be addressed before the Django upgrade is complete.
