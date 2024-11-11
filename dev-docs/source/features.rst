Application Features
====================

The following features are implemented in the application:

* :doc:`Dynamic API endpoint creation based on Amsterdam Schema <dynamic_api>`.
* :doc:`Dynamic Django model construction <dynamic_models>`.
* :doc:`REST API Endpoint based on DSO specification <compliance>`.

 * REST Pagination (:samp:`?page={n}`, :samp:`?_pageSize={n}`).
 * REST sideloading (``?_expand=true`` / :samp:`?_expandScope={field},{field..}`).
 * REST field limiting (:samp:`?_fields={field1},{field...},-{field..}` using filtersets).
 * REST filtering (:samp:`?{field}={...}` / :samp:`?{field}[{operator}]={...}`).
 * REST HAL ``_links`` section.
 * REST ``application/problem+json`` exception messages.
 * Temporal relations (``identificatie``, ``volgnummer``, :samp:`?geldigOp={date}`).

* :doc:`WFS Endpoint for Geo applications <wfs>`.
* :doc:`Datasets with a remote endpoint <remote>`.
* :doc:`Authentication using scopes <auth>`.
* :doc:`Temporal browsing <temporal>`.
* :doc:`Streaming output formats <streaming>`:

 * HAL-JSON (``?_format=json``, the default except for browsers)
 * CSV export (``?_format=csv``)
 * GeoJSON export (``?_format=csv``)

* :doc:`OpenAPI spec <openapi>`.
* Audit logging for requests.
* Browsable API (default for browsers).
* Azure BLOB fields for large documents.
* Internal schema reload endpoint (though unused).
* :doc:`Database roles to have per-user permissions <database>`.
