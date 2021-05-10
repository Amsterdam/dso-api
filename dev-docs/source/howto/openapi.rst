OpenAPI Schema Testing
======================

OpenAPI schema can be verified on localhost using following command:

.. code-block:: console

    OPENAPI_HOST=http://localhost:8000 ./.jenkins/openapi_validator/run_validator.sh

Do not forget to replace ``OPENAPI_HOST`` with address of running DSO-API,
in case it differs from ``http://localhost:8000``.
