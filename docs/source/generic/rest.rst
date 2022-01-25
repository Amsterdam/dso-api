.. _rest_api_generic:

REST API gebruiken
==================

Alle nieuwe DSO-gebaseerde API's zijn te vinden onder het
`https://api.data.amsterdam.nl/v1/ <https://api.data.amsterdam.nl/api/swagger/?url=/v1/>`_ endpoint.
De individuele datasets worden toegelicht op de :doc:`datasets </datasets/index>` pagina.

.. tip::
    Een overzicht van alle DataPunt API's is te vinden op: https://api.data.amsterdam.nl/.

De datasets ondersteunen de volgende HTTP operaties:

.. list-table::
    :widths: 50 50
    :header-rows: 1

    * - Verzoek
      - Resultaat
    * - :samp:`GET /v1/{dataset}/{tabel}/`
      - De lijst van alle records in een tabel
    * - :samp:`GET /v1/{dataset}/{tabel}/{id}/`
      - Een individueel record uit de tabel

Bijvoorbeeld:

.. code-block:: bash

    curl https://api.data.amsterdam.nl/v1/gebieden/buurten/
    curl https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000092.1/

Wanneer een pagina direct met de browser opgevraagd wordt
dan worden de resultaten als een doorklikbare HTML pagina getoond.
Bijvoorbeeld: https://api.data.amsterdam.nl/v1/gebieden/buurten/.
Door de header ``Accept: application/hal+json`` te sturen wordt
altijd een JSON response geforceerd. Dit kan ook met de query parameter :samp:`_format=json`

.. rubric:: Functionaliteit

De API's ondersteunen mogelijkheden tot:

.. toctree::
    :maxdepth: 1

    rest/pagination
    rest/filtering
    rest/fields
    rest/sort
    rest/embeds
    rest/formats
    rest/projections
    rest/temporal


De DSO Standaard
----------------

De API's op het ``/v1/`` endpoint volgen de landelijke
`DSO standaard <https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/>`_
om een eenduidige wijze te bieden voor afnemers.

Hierdoor kom je als technisch gebruiker o.a. de volgende elementen tegen:

* HAL-JSON links, zoals: ``{"_links": {"self": {"href": ..., "title": ...}}}``
* Met :doc:`?_expandScope={veld1},{veld2} <rest/embeds>` worden relaties getoond in de ``_embedded`` sectie.
* Met :doc:`?_expand=true <rest/embeds>` worden alle relaties uitgevouwen in de ``_embedded`` sectie.
* Met :doc:`?_fields=... <rest/fields>` kunnen een beperkte set van velden opgevraagd worden.
* :doc:`Sortering <rest/sort>` met :samp:`?_sort={veldnaam},-{desc veldnaam}`
* :doc:`Filtering <rest/filtering>` op velden via de query-string.
* :doc:`Tijdreizen <rest/temporal>` met de ``?geldigOp=...`` parameter.
* :doc:`Paginering <rest/pagination>` en ``X-Pagination-*`` headers.
* Responses geven het object terug, zonder envelope.
