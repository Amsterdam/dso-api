Dataset versioning
==================

DSO API provides option to serve multiple versions of same dataset via API and Database.

This document aims to cover technical details on how DSO API behaves in different scenarios,
depending on Dataset model configuration.


How dataset version is defined
------------------------------

:code:`Dataset` model exposes 2 parameters to control versioning

:code:`Dataset.version`
  string, formatted according to `Semantic Versioning standard <https://semver.org/>`_ e.g. :code:`0.1.0`
   (:code:`<major> "." <minor> "." <patch>`).
:code:`Dataset.is_default_version`
   boolean, defaults to :code:`True`

Combination of these 2 parameters defines how API and Database behave.

Verion consists of 3 numbers :code:`MAJOR.MINOR.PATCH`:

 :code:`MAJOR` version brings backwards incompatible change, suchs as:
  * Table removal
  * Field removal
  * Field rename

 :code:`MINOR` version is fully backwards compatible:
  * Field addition (all fields are optional)
  * Table addition

 :code:`PATCH` version contains metadata changes only and is not reflected in data structure.


Datasets without version definition and default versions of datasets
--------------------------------------------------------------------

All datasets without version definition in :code:`Dataset.version` or with :code:`Dataset.is_default_version == True`
will be treated as not versioned and all tables within dataset will have API endpoint set to

:code:`/v1/<dataset.url_prefix>/<dataset.id>/<table.name>/`

Database tables of this dataset will be prefixed with :code:`<dataset.id>_`


Datasets with non-default versions
----------------------------------

Any dataset with :code:`version` defined and :code:`is_default_version` set to :code:`False` will have API endpoint defined as:

 :code:`/v1/<dataset.url_prefix>/<dataset.id>@<dataset.version>/<table.name>/`


Database structure
------------------

All tables within default version of Dataset will have :code:`<dataset.id>_` name prefix.

Other Dataset versions will have major version taken into table name prefix:
:code:`<dataset.id>_<dataset.version.major>_`

Examples:
=========

Given following Dataset definition:

 - :code:`test` dataset with version :code:`0.1.0` and single table :code:`users` (fields: :code:`id`, :code:`name`) defined
 - :code:`test` dataset with version :code:`0.1.1` is default and single table :code:`users` (fields: :code:`id`, :code:`name`, :code:`age`) defined
 - :code:`test` dataset with version :code:`1.0.1` and 2 tables defined: :code:`users` (fields: :code:`id`, :code:`firstName`, :code:`lastName`) and :code:`locations` (fields: :code:`id`, :code:`name`)

API structure:
--------------

Non-default versions of datasets will not be exposed via REST or WFS API.

Database structure:
-------------------

Database will have 3 tables defined:

- :code:`test_users` with columns: :code:`id`, :code:`name`, :code:`age`. Used by :code:`0.1.0` and :code:`0.1.1` users APIs.
- :code:`test_1_users` with columns: :code:`id`, :code:`firstName`, :code:`lastName`. Used by :code:`1.0.1` users API.
- :code:`test_1_locations` with columns: :code:`id`, :code:`name`. Used by :code:`1.0.1` locations API.


Relation versioning
===================

Cross dataset relation tables will have major version numbers at all times, making relations persistent.

This means relation from :code:`sportparken@1.0.0.sportparken.buurten` and :code:`bag@2.0.0.buurt.id` and will look like:

:code:`sportparken_1_sportparken_buurten`
