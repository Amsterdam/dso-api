Filtering
=========

Filteren op attributen
----------------------

Ieder veld kan gebruikt worden om op te filteren.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam=Westpoort'

Als het veld een array van objecten is, kunnen de subvelden van de objecten
gefilterd worden met de naam van de array en de naam van het subveld gescheiden
door een punt.
Voorbeeld: het veld

.. code-block:: json

    "gebruiksdoel": {
      "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "code": {
              "type": "string"
            }
          }
        }
      }

kan gefilterd worden met:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/verblijfsobjecten/?gebruiksdoel.code=1'


Filteren in relaties
--------------------

De relaties, en attributen van relaties, kunnen gebruikt worden in filters.
Verbind de velden door middel van een punt-notatie (``relatie.veldnaam``).

Bijvoorbeeld bij een enkelvoudige relatie:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/huishoudelijkafval/container/?locatie.id=10009'

...een temporele relatie:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/bag/verblijfsobjecten/?heeftHoofdadres.identificatie=0363200000006110&heeftHoofdadres.volgnummer=1'

...of een relatie zonder volgnummer, die altijd verwijst naar het laatste voorkomen:

.. code-block:: bash

    curl 'http://api.data.amsterdam.nl/v1/huishoudelijkafval/container/?locatie.gbdBuurt.identificatie=03630000000770'

Je kan ieder ander veld uit de relatie ook gebruiken, zoals bijvoorbeeld ``?locatie.status=0``
of een genest veld: ``?locatie.gbdBuurt.identificatie=...``. Deze opties staan niet in het naslagwerk
vermeld, maar kunnen wel samengesteld worden door de velden van de API of documentatie te combineren.
Het zoeken op de identificatie (primaire sleutel) is het snelste,
en de beste keuze als je de identificatie ook weet.

Operatoren
----------

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

De ``like``-operator maakt *fuzzy search* met jokertekens (*wildcards*) mogelijk.
Het teken ``*`` staat voor nul of meer willekeurige tekens, ``?`` staat voor precies één willekeurig teken.
Alle andere tekens staan voor zichzelf.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=West*'

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=??st'

``naam[like]=West*`` selecteert alle rijen in een dataset waarvan de naam begint met "West",
inclusief stadsdeel West.
Rijen waarvan de naam "West" *bevat* kunnen gevonden worden met ``*West*``.
De zoekterm ``??st`` selecteert "Oost" en "West": twee willekeurige tekens, gevolgd door "st".

Als de filtertekst geen jokertekens bevat gedraagt ``like`` zich hetzelfde als ``exact``.
Er is geen *escaping* van de jokertekens mogelijk.

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

Bij het doorzoeken van geometrievelden wordt gebruik gemaakt van de projectie opgegeven in de header ``Accept-CRS``.
Afhankelijk van de projectie wordt x,y geïnterpreteerd als longitude, latitude of x,y in RD of anderszins.
Indien ``Accept-CRS`` niet wordt meegegeven worden x en y, afhankelijk van de waardes,
geinterpreteerd als longitude en latitude in ``EPSG:4326`` of ``EPSG:28992``.
