.. _rest_api_generic:

REST API gebruiken
==================

Alle nieuwe DSO-gebaseerde API's zijn te vinden onder het
`https://api.data.amsterdam.nl/v1/ <https://api.data.amsterdam.nl/api/swagger/?url=/v1/>`_ endpoint.
De individuele datasets worden toegelicht op de :doc:`datasets <../datasets/index>` pagina.

.. tip::
    Een overzicht van alle DataPunt API's is te vinden op: https://api.data.amsterdam.nl/.

De datasets ondersteuneb de volgende HTTP operaties:

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

De API's ondersteunen daarnaast mogelijkheden tot:

* `Paginering`_
* `Filtering`_
* `Sorteren van resultaten`_
* `Embedding van relaties`_
* `Exportformaat opgeven`_
* `Geometrie projecties`_


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


Filtering
---------

Ieder veld kan gebruikt worden om op te filteren.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam=Westpoort'

Afhankelijk van het veldtype zijn er extra operatoren mogelijk.

.. tip::
    De exacte namen en mogelijke velden per tabel zijn op de :doc:`REST API Datasets <../datasets/index>` pagina te zien.

Voor alle veldtypes
~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Operator
     - Werking
     - SQL Equivalent
   * - :samp:`?{veld}[in]={x},{y}`
     - De waarde moet één van de opties zijn.
     - :samp:`{veld} IN ({x}, {y})`
   * - :samp:`?{veld}[not]={x}`
     - De waarde moet niet voorkomen.
     - :samp:`{veld} != {x}`.
   * - :samp:`?{veld}[isnull]=true`
     - Het veld mag niet ingevuld zijn.
     - :samp:`{veld} IS NULL`
   * - :samp:`?{veld}[isnull]=false`
     - Het veld moet ingevuld zijn.
     - :samp:`{veld} IS NOT NULL`

Bij waarden met getallen
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Operator
     - Werking
     - SQL Equivalent
   * - :samp:`?{veld}[lt]={x}`
     - Test op kleiner dan (lt=Less Then)
     - :samp:`{veld} < {x}`
   * - :samp:`?{veld}[lte]={x}`
     - Test op kleiner dan of gelijk (lte: less then or equal to)"
     - :samp:`{veld} <= {x}`
   * - :samp:`?{veld}[gt]={x}`
     - Test op groter dan (gt=greater then)
     - :samp:`{veld} > {x}`
   * - :samp:`?{veld}[gte]={x}`
     - Test op groter dan of gelijk aan (gte: greater then or equal to)
     - :samp:`{veld} >= {x}`

Bij waarden met tekst
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Operator
     - Werking
     - SQL Equivalent
   * - :samp:`?{tekstveld}[like]={x}`
     - Zoekt in tekstgedeelte met jokertekens (``*`` en ``?``).
     - :samp:`{tekstveld} LIKE '{x}'`
   * - :samp:`?{tekstveld}[isempty]=true`
     - Waarde moet leeg zijn
     - :samp:`{veld} IS NULL OR {veld} = ''`
   * - :samp:`?{tekstveld}[isempty]=false`
     - Waarde mag niet niet leeg zijn
     - :samp:`{veld} IS NOT NULL AND {veld} != ''`

De ``like`` operator ondersteund jokertekens (wildcards).
Het teken ``*`` staat voor nul of meer willekeurige tekens, ``?`` staat voor precies één willekeurig teken.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=West*'

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=Westp??rt'

Er is geen *escaping* van deze symbolen mogelijk.

Bij waarden met lijsten
~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Operator
     - Werking
     - SQL Equivalent

   * - :samp:`?{arrayveld}[contains]={x},{y}`
     - De lijst moet beide bevatten.
     - :samp:`({x}, {y}) IN {arrayveld}`

Bij waarden met een geometrie
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Operator
     - Werking
     - SQL Equivalent
   * - :samp:`?{geoveld}[contains]={x},{y}`
     - Geometrie moet voorkomen op een punt (intersectie)
     - :samp:`ST_Intersects({geoveld}, POINT({x} {y}))`
   * - :samp:`?{geoveld}[contains]=POINT(x y)`
     - Idem, nu in de WKT (well-known text) notatie.
     - :samp:`ST_Intersects({geoveld}, POINT({x} {y}))`

Het gebruikte coordinatenstelsel en  Bij het doorzoeken van geometrie velden wordt gebruik gemaakt van de proje opgegeven ``Accept-CRS`` header.
Afhankelijk van de projectie wordt x,y geïnterpreteerd als longitude, latitude of x,y in RD of anderszins.
Indien ``Accept-CRS`` niet wordt meegegeven worden x en y, afhankelijk van de waardes,
geinterpreteerd als longitude en latitude in ``EPSG:4326`` of ``EPSG:28992``.


Specifieke velden opvragen
--------------------------

Gebruik de :samp:`?_fields={veld1},{veld2},{...}` parameter om alleen specifieke velden te ontvangen:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?fields=geometry,soortPaaltje'

Als de veldnamen voorafgegaan worden door een minteken, dan worden alle velden behalve de genoemde
opgestuurd:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?fields=-area,-noodzaak'


Sorteren van resultaten
-----------------------

Gebruik de parameter :samp:`?_sort={veld1},{veld2},{...}` om resultaten te ordenen.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=naam'

Sorteren om meerdere velden is ook mogelijk met :samp:`?_sort={veld1},{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=ingangCyclus,naam'

Gebruik het ``-``-teken om omgekeerd te sorteren :samp:`?_sort=-{veld1},-{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=-ingangCyclus,naam'


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

Exportformaat opgeven
---------------------

De API kan de resultaten in andere bestandsformaten presenteren,
zodat deze gegegevens direct in de bijbehorende software ingeladen kan worden.
Standaard wordt de HAL-JSON notatie gebruikt uit de DSO standaard.

Met het CSV formaat kunnen de gegevens direct in Excel worden ingelezen.

Met de ``?_format=`` parameter kan dit gewijzigd worden.
De volgende formaten worden ondersteund:

.. list-table::
    :widths: 20 40 40
    :header-rows: 1

    * - Parameter
      - Toelichting
      - Media type
    * - ``?_format=json``
      - HAL-JSON notatie (standaard)
      - ``application/hal+json``
    * - ``?_format=geojson``
      - GeoJSON notatie
      - ``application/geo+json``
    * - ``?_format=csv``
      - Kommagescheiden bestand
      - ``text/csv``

.. warning::
    Niet ieder exportformaat ondersteund alle veldtypen die een dataset kan bevatten.
    Bij het gebruik van een CSV bestand worden de meer-op-meer relaties niet opgenomen in de export.
    In een GeoJSON bestand worden ingesloten velden opgenomen als losse objecten.

.. tip::
   Voor het koppelen van de datasets in GIS-applicaties kun je naast het GeoJSON formaat
   ook gebruik maken van de :doc:`WFS koppeling <wfs>`.

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
