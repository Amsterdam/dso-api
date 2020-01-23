schematools
===========

Tooling to work with Amsterdam schema files.


Installation
------------

Install with: `pip install schematools`


Usage
-----

The core code is in the `db` module. There are python functions to
create/delete a table and to add rows from an ndjson file.  The modules can be
used from the command-line, or integrated in a Django application.


From the command-line, the modules can be invoke with::

 - schema create dataset <path-to-schema> [-t <tablename>]
 - schema create records <path-to-schema> <path-to-ndjson>
 - schema delete dataset <path-to-schema> [-t <tablename>]

Example
-------

A small example has been added that shows how the dynamic Django model generation from an
amsterdam schema can be used in Django REST framework.
