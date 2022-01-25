Werken met QGIS
===============

De WFS lagen zijn beschikbaar onder de volgende URL's:

:samp:`https://api.data.amsterdam.nl/v1/wfs/{<dataset naam>}/`

Gebruik zo'n URL in QGIS:

.. figure:: /generic/images/qgis-add-wfs.png
   :width: 1340
   :height: 1582
   :scale: 25%
   :alt: (voorbeeldafbeelding van QGIS)

   In de bovenstaande afbeelding wordt QGIS gekoppeld met de BAG dataset:
   https://api.data.amsterdam.nl/v1/wfs/bag/

Voor gesloten datasets moet ook een authorisatie configuratie worden toegevoegd. Dit kan door
op het groene kruisje in het bovenstaande menu te klikken. Selecteer OAuth2 authenticatie, met 'implicit' grant flow.
Vul bij 'request url' :samp:`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/auth` en bij 'token url'
:samp:`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/token` in.
De client id is :samp:`qgis` en access method is :samp:`header`. QGIS zal bij het gebruiken van de WFS een browserscherm openen,
waar een geauthoriseerde gebruiker kan inloggen.

.. figure:: /generic/images/qgis-add-authentication.png
   :width: 1340
   :height: 1582
   :scale: 25%
   :alt: (voorbeeldafbeelding van QGIS authenticatie)

   In de bovenstaande afbeelding wordt QGIS authenticatie configuratie ingevoerd.

Hierna zijn de gegevens te raadplegen, te filteren en te combineren:

.. figure:: /generic/images/qgis-bag.png
   :width: 2438
   :height: 1614
   :scale: 25%
   :alt: (stadsdelen weergegeven in QGIS)

.. tip::
    De parameters ``?SERVICE=WFS&VERSION=2.0.0&REQUEST=..`` worden door QGIS zelf achter de URL gezet.
    Het is niet nodig deze zelf toe te voegen.

.. tip::
    De schuine streep aan het einde van de URL is belangrijk.
    QGIS werkt niet als deze ontbreekt. Dit is een beperking
    in QGIS.

Queries op relaties
-------------------

Om object-relaties uit te lezen in de WFS server,
kan je de volgende optie toevoegen aan de URL:

* :samp:`?embed={relatienaam},{...}` zal een veld platgeslagen invoegen.
* :samp:`?expand={relatienaam},{...}` zal een veld als "complex feature" invoegen.

Gebruik deze URL in QGIS, of een ander GIS-pakket.

Als voorbeeld: de BAG feature type *buurt* een relatie met een *stadsdeel*.
Deze kan op beide manieren geconfigureerd worden in een GIS-pakket:

* ``https://api.data.amsterdam.nl/v1/wfs/bag/?embed=stadsdeel`` levert een `stadsdelen met platgeslagen dot-notate <https://api.data.amsterdam.nl/v1/wfs/bag/?embed=stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=buurt&COUNT=5>`_.
* ``https://api.data.amsterdam.nl/v1/wfs/bag/?expand=stadsdeel`` levert een `stadsdelen als complex feature <https://api.data.amsterdam.nl/v1/wfs/bag/?expand=stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=buurt&COUNT=5>`_.

Deze parameters kunnen gecombineerd worden met de ``OUTPUTFORMAT`` parameter,
zodat het export formaat ook geneste relaties bevat.

.. admonition:: Embed of expand gebruiken?

   QGIS 3 heeft geen ondersteuning voor complex features, en verwerkt deze als tekst.
   Gebruikt in QGIS daarom alleen de platgeslagen versie met :samp:`?embed={...}`.
   De :samp:`?expand={...}` versie is daarentegen ideaal voor GeoJSON exports,
   die wel goed kan omgaan met geneste structuren.

Datasets met meerdere geometrieën
---------------------------------

Indien een tabel meerdere geometriëen bevat, zal deze voor ieder geometrie veld los opgenomen worden in de WFS.
Zodoende kunnen GIS-pakketten op beide geometrieën weergeven op de kaart.

Dit is bijvoorbeeld te zien bij Horeca-exploitatievergunningen: er wordt een aparte laag voor het pand,
en de bijbehorende terrassen beschikbaar gesteld. Zodoende kunnen beide geometriën uitgelezen worden.
De data van beide lagen is identiek; alleen de volgorde van geometrie-velden is aangepast.
