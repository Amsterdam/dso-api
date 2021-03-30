# Dataset versioning (DRAFT)

DSO API provides option to serve multiple versions of same dataset via API and Database.

This document aims to cover technical details on how DSO API behaves in different scenarios, 
depending on Dataset model configuration.


## How dataset version is defined

`Dataset` model exposes 2 parameters to control versioning:

 - `Dataset.version`: string, formatted according to [Semantic Versioning standard](https://semver.org/) e.g. `0.1.0` 
   (`<major> "." <minor> "." <patch>`).
 - `Dataset.is_default_version`: boolean, defaults to `True`

Combination of these 2 parameters defines how API and Database behave.

Verion consists of 3 numbers `MAJOR.MINOR.PATCH`:

 `MAJOR` version brings backwards incompatible change, suchs as: 
  - Table removal
  - Field removal
  - Field rename

 `MINOR` version is fully backwards compatible:
  - Field addition (all fields are optional)
  - Table addition
  
 `PATCH` version contains metadata changes only and is not reflected in data structure.
 

## Datasets without version definition and default versions of datasets

All datasets without version definition in `Dataset.version` or with `Dataset.is_default_version == True` 
will be treated as not versioned and all tables within dataset will have API endpoint set to 

> `/v1/<dataset.url_prefix>/<dataset.id>/<table.name>/`

Database tables of this dataset will be prefixed with `<dataset.id>_`


## Datasets with non-default versions

Any dataset with `version` defined and `is_default_version` set to `False` will have API endpoint defined as:

 > `/v1/<dataset.url_prefix>/<dataset.id>@<dataset.version>/<table.name>/`


## Database structure

All tables within default version of Dataset will have `<dataset.id>_` name prefix.

Other Dataset versions will have major version taken into table name prefix:
> `<dataset.id>_<dataset.version.major>_`

# Examples:

Given following Dataset definition:

 - `test` dataset with version `0.1.0` and single table `users` (fields: `id`, `name`) defined
 - `test` dataset with version `0.1.1` is default and single table `users` (fields: `id`, `name`, `age`) defined
 - `test` dataset with version `1.0.1` and 2 tables defined: `users` (fields: `id`, `firstName`, `lastName`) and `locations` (fields: `id`, `name`)

### API structure:

Non-default versions of datasets will not be exposed via REST or WFS API.

### Database structure:

Database will have 3 tables defined: 

- `test_users` with columns: `id`, `name`, `age`. Used by `0.1.0` and `0.1.1` users APIs.
- `test_1_users` with columns: `id`, `firstName`, `lastName`. Used by `1.0.1` users API.
- `test_1_locations` with columns: `id`, `name`. Used by `1.0.1` locations API.
   

# Relation versioning

Cross dataset relation tables will have major version numbers at all times, making relations persistent.

This means relation from `sportparken@1.0.0.sportparken.buurten` and `bag@2.0.0.buurt.id` and will look like:

`sportparken_1_sportparken_buurten`
