.. _rest_api_generic:

REST API gebruiken
==================

Alle nieuwe DSO-gebaseerde API's zijn te vinden onder het
`https://api.data.amsterdam.nl/v1/ <https://api.data.amsterdam.nl/api/swagger/?url=/v1/>`_ endpoint.
De individuele datasets worden toegelicht op de :doc:`datasets <../datasets/index>` pagina.

.. tip::
    Een overzicht van alle DataPunt API's is te vinden op: https://api.data.amsterdam.nl/.


Uitlezen van de API
-------------------

De volgende HTTP operaties worden ondersteund:

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


Paginering
----------

De resultaten worden gepagineerd teruggegeven.
De paginagrootte kan aangepast worden door een :samp:`?_pageSize={n}` query parameter toe te voegen aan de request URL.

In de response zijn de volgende elementen te vinden:

.. code-block:: javascript

    {
        "_links": {
            "self": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/"
            },
            "next": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/?page=2"
            },
            "previous": {
                "href": null
            }
        },
        "_embedded": {

           // alle objecten...

        },
        "page": {
            "number": 1,
            "size": 20,
            "totalElements": 973,
            "totalPages": 49
        }
    }

Met het ``_links.next`` en ``_links.previous`` veld zijn respectievelijk de volgende en vorige pagina op te vragen.
In het ``page`` object zijn de volgende velden opgenomen:

* ``page.number``: Het huidige paginanummer.
* ``page.size``: De grootte van een pagina.
* ``page.totalElements``: Het totaal aantal records over alle pagina's heen.
* ``page.totalPages``: Het totaal aantal pagina's,

De velden uit het ``page`` object worden ook als HTTP headers in de response teruggegeven:

* ``X-Pagination-Page``: Het huidige paginanummer.
* ``X-Pagination-Limit``: de grootte van een pagina.
* ``X-Pagination-Count``: Optioneel, het totaal aantal pagina's.
* ``X-Total-Count``: Optioneel, het totaal aantal records over alle pagina's heen.

Sortering van resultaten
------------------------

Gebruik de parameter :samp:`?_sort={veld1},{veld2},{...}` om resultaten te ordenen.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?_sort=naam'

Sorteren om meerdere velden is ook mogelijk met :samp:`?_sort={veld1},{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?_sort=ingangCyclus,naam'

Gebruik het ``-``-teken om omgekeerd te sorteren :samp:`?_sort=-{veld1},-{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?_sort=-ingangCyclus,naam'


Specifieke velden opvragen
--------------------------

Gebruik de :samp:`?_fields={veld1},{veld2},{...}` parameter om alleen specifieke velden te ontvangen:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?fields=geometry,soortPaaltje'

Als de veldnamen voorafgegaan worden door een minteken, dan worden alle velden behalve de genoemde
opgestuurd:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?fields=-area,-noodzaak'



Filtering
---------

Ieder veld kan gebruikt worden om op te filteren.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?naam=Westpoort'

Naast een exacte match zijn er afhankelijk van het type veld ook andere operatoren mogelijk:

* :samp:`?{veld}[lt]={x}` werkt als "less then": :samp:`{veld} < {x}`.
* :samp:`?{veld}[lte]={x}` werkt als "less then or equal to": :samp:`{veld} <= {x}`.
* :samp:`?{veld}[gt]={x}` werkt als "greather then": :samp:`{veld} > {x}`.
* :samp:`?{veld}[gte]={x}` werkt als "greather then or equal to": :samp:`{veld} >= {x}`.
* :samp:`?{veld}[in]={x},{y}` werkt als :samp:`{veld} IN ({x}, {y})`.
* :samp:`?{veld}[contains]={x},{y}` werkt als :samp:`({x}, {y}) IN {veld}` (voor array velden).
* :samp:`?{veld}[contains]={x},{y}|POINT(x y)` selecteert die objecten waarbij punt x,y in het
  (multi-)polygon :samp:`veld` ligt. Afhankelijk van de waarde van header Accept-CRS wordt x,y
  geinterpreteerd als longitude, latitude of x,y in RD of anderszins. Indien Accept-CRS niet wordt
  meegegeven worden x en y, afhankelijk van de waardes, geinterpreteerd als longitude en latitude
  in EPSG:4326 of EPSG:28992.
* :samp:`?{veld}[not]={x}` werkt als :samp:`{veld} != {x}`.
* :samp:`?{veld}[isnull]={true|false}` werkt als :samp:`{veld} IS NULL` of :samp:`{veld} IS NOT NULL`.
* :samp:`?{veld}[isempty]={true|false}` werkt als :samp:`{veld} IS NULL OR {veld} = ''`
  of :samp:`{veld} IS NOT NULL AND {veld} <> ''`.

Tekstvelden ondersteunen wildcards. Maak daarvoor gebruik van de :samp:`?{veld}[like]` operator:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?naam[like]=West*'

    curl 'https://api.data.amsterdam.nl/v1/bag/stadsdeel/?naam[like]=Westp??rt'

``*`` staat voor nul of meer willekeurige tekens. ``?`` staat voor precies
één willekeurig teken. Er is geen *escaping* van deze symbolen mogelijk.

De namen van de velden en mogelijke operatoren zijn te vinden op
de :doc:`datasets <../datasets/index>` pagina.


Embedding van relaties
----------------------

Bij iedere relatie wordt er een hyperlink meegegeven om het object op te vragen.
Echter kunnen alle objecten ook in een enkele request opgehaald worden.
Dit is zowel voor de client als server efficienter.

Gebruik hiervoor één van volgende opties:

* Door ``?_expand=true`` worden alle relaties uitgevouwen in de ``_embedded`` sectie.
* Door :samp:`?_expandScope={veld1},{veld2}` worden specifieke relaties getoond in de ``_embedded`` sectie.

De volgende aanroepen zijn identiek:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/buurten/?_expand=true'

    curl 'https://api.data.amsterdam.nl/v1/gebieden/buurten/?_expandScope=ligtInWijk'

De response bevat zowel het "buurt" object als de "wijk":

.. code-block:: javascript

    {
        "_links": {
            // ...
        },
        "_embedded": {
            "buurten": [
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#buurten",
                        "self": {
                            "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                            "title": "03630000000078.1",
                            "volgnummer": 1,
                            "identificatie": "03630000000078"
                        },
                        "bestaatUitBuurtenGgwgebieden": [
                            {
                                "href": "https://api.data.amsterdam.nl/v1/gebieden/ggwgebieden/03630950000000/?volgnummer=1",
                                "title": "03630950000000.1",
                                "volgnummer": 1,
                                "identificatie": "03630950000000"
                            },
                            {
                                "href": "https://api.data.amsterdam.nl/v1/gebieden/ggwgebieden/03630950000000/?volgnummer=2",
                                "title": "03630950000000.2",
                                "volgnummer": 2,
                                "identificatie": "03630950000000"
                            }
                        ],
                        "bestaatUitBuurtenGgpgebieden": [
                            {
                                "href": "https://api.data.amsterdam.nl/v1/gebieden/ggpgebieden/03630940000000/?volgnummer=1",
                                "title": "03630940000000.1",
                                "volgnummer": 1,
                                "identificatie": "03630940000000"
                            }
                        ],
                        "buurtenWoningbouwplan": [],
                        "buurtenStrategischeruimtes": [],
                        "ligtInWijk": {
                            "href": "https://api.data.amsterdam.nl/v1/gebieden/wijken/03630012052036/?volgnummer=1",
                            "title": "03630012052036.1",
                            "volgnummer": 1,
                            "identificatie": "03630012052036"
                        }
                    },
                    "code": "A00a",
                    "naam": "Kop Zeedijk",
                    "cbsCode": "BU03630000",
                    "geometrie": {
                        "type": "Polygon",
                        "coordinates": [
                            // ...
                        ]
                    },
                    "ligtInWijkVolgnummer": 1,
                    "ligtInWijkIdentificatie": "03630012052036",
                    "ligtInWijkId": "03630012052036",
                    "documentdatum": null,
                    "documentnummer": null,
                    "eindGeldigheid": null,
                    "beginGeldigheid": "2006-06-12",
                    "registratiedatum": "2018-10-25T12:17:48",
                    "id": "03630000000078.1"
                }
            ],
            "ligtInWijk": [
                {
                    "_links": {
                        "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#wijken",
                        "self": {
                            "href": "https://api.data.amsterdam.nl/v1/gebieden/wijken/03630012052036/?volgnummer=1",
                            "title": "03630012052036.1",
                            "volgnummer": 1,
                            "identificatie": "03630012052036"
                        },
                        "ligtInStadsdeel": {
                            "href": "https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/03630000000018/?volgnummer=3",
                            "title": "03630000000018.3",
                            "volgnummer": 3,
                            "identificatie": "03630000000018"
                        }
                    },
                    "code": "A00",
                    "naam": "Burgwallen-Oude Zijde",
                    "cbsCode": "WK036300",
                    "geometrie": {
                        "type": "Polygon",
                        "coordinates": [
                            // ...
                        ]
                    },
                    "documentdatum": null,
                    "documentnummer": null,
                    "eindGeldigheid": null,
                    "beginGeldigheid": "2006-06-12",
                    "ligtInStadsdeelVolgnummer": 3,
                    "ligtInStadsdeelIdentificatie": "03630000000018",
                    "registratiedatum": "2018-10-25T12:17:33",
                    "id": "03630012052036.1"
                }
            ]
        },
        "page": {"number": 1, "size": 1, "totalElements": 973, "totalPages": 973}
    }

Geometrie projecties
--------------------

De geometrie velden worden standaard teruggegeven in de projectie van de originele bron.
Dit is veelal de rijksdriehoekscoördinaten (Amersfoort / RD New).
Met de ``Accept-Crs`` header kan opgegeven worden met welke transformatie
alle geometriewaarden teruggegeven moet worden. Bijvoorbeeld:

.. code-block:: bash

    curl -H "Accept-Crs: EPSG:28992" https://api.data.amsterdam.nl/v1/gebieden/buurten/

Veelgebruikte projecties zijn:

.. list-table::
    :widths: 30 70
    :header-rows: 1

    * - Projectie
      - Toelichting
    * - ``EPSG:28992``
      - Nederlandse rijksdriehoekscoördinaten (RD New).
    * - ``EPSG:4258``
      - ETRS89, Europese projectie.
    * - ``EPSG:3857``
      - Pseudo-Mercator (vergelijkbaar met Google Maps)
    * - ``EPSG:4326``
      - WGS 84 latitude-longitude, wereldwijd.

De andere notatievormen (zoals ``urn:ogc:def:crs:EPSG::4326`` en ``www.opengis.net`` URI's)
worden ook ondersteund.


De DSO Standaard
----------------

De API's op het ``/v1/`` endpoint volgen de landelijke
`DSO standaard <https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/>`_
om een eenduidige wijze te bieden voor afnemers.

Hierdoor kom je als technisch gebruiker o.a. de volgende elementen tegen:

* HAL-JSON links, zoals: ``{"_links": {"self": {"href": ..., "title": ...}}}``
* Met :samp:`?_expandScope={veld1},{veld2}` worden relaties getoond in de ``_embedded`` sectie.
* Met ``?_expand=true`` worden alle relaties uitgevouwen in de ``_embedded`` sectie.
* Met ``?_fields=...`` kunnen een beperkte set van velden opgevraagd worden.
* Sortering met :samp:`?_sort={veldnaam},-{desc veldnaam}`
* Filtering op velden via de query-string.
* Responses geven het object terug, zonder envelope.
* Responses met paginering en ``X-Pagination-*`` headers.
