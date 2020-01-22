schematools
===========

Tooling to work with Amsterdam schema files.


Installation
------------

Install with: `pip install schematools`


Usage
-----

The core code is in the `db` module. There are python functions to create/delete a table and to add rows from a ndjson file.
The modules can be used from the command-line, or integrated in a django application.


From the command-line, the modules can be invoke with:

 - schema create dataset <path-to-schema> [-t <tablename>]
 - schema create records <path-to-schema> <path-to-ndjson>
 - schema delete dataset <path-to-schema> [-t <tablename>]
