Werken met QGIS
===============

WFS
---

De WFS-lagen zijn beschikbaar onder de volgende URL's:

:samp:`https://api.data.amsterdam.nl/v1/wfs/{<dataset>}/`

Gebruik zo'n URL in QGIS:

.. figure:: /generic/images/qgis-add-wfs.png
   :width: 1340
   :height: 1582
   :scale: 25%
   :alt: (voorbeeldafbeelding van QGIS)

   In de bovenstaande afbeelding wordt QGIS gekoppeld met de BAG dataset:
   https://api.data.amsterdam.nl/v1/wfs/bag/

.. tip::
    De parameters ``?SERVICE=WFS&VERSION=2.0.0&REQUEST=..`` worden door QGIS zelf achter de URL gezet.
    Het is niet nodig deze zelf toe te voegen.

.. tip::
    De schuine streep aan het einde van de URL is belangrijk.
    QGIS werkt niet als deze ontbreekt. Dit is een beperking
    in QGIS.

Vector tiles (MVT)
------------------

De volgende stappen moeten uitgevoerd worden om vector tiles in QGIS te laden:

* In de *Browser* (linker tabblad), rechtermuisklik op *Vector Tiles*,
  dan *Nieuwe algemene verbinding* (*New Generic Connection*).
* De URL is ``https://api.data.amsterdam.nl/v1/mvt/<dataset>/<tabel>/{z}/{x}/{y}.pbf``.
  Vervang ``<dataset>`` en ``<tabel>`` door de namen in kwestie,
  maar laat ``{z}/{x}/{y}`` staan, inclusief de accolades.
* *Min. zoomniveau* (*Min. Zoom Level*) staat standaard op 0. Zet dit op 1.

Een lijst van datasets die vector tiles ondersteunen is beschikbaar op:
https://api.data.amsterdam.nl/v1/mvt/.


Autorisatie
-----------

Voor gesloten datasets moet ook een autorisatieconfiguratie worden toegevoegd. Dit kan door
op het groene kruisje in het bovenstaande menu te klikken. Selecteer OAuth2-authenticatie, met 'implicit' grant flow.
Vul bij 'request url' :samp:`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/auth` en bij 'token url'
:samp:`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/certs` in.
De client id is :samp:`qgis`, Scope is :samp:`email` en access method is :samp:`header`.
QGIS zal bij het activeren van een kaartlaag een browserscherm openen,
waarin gebruikersnaam en wachtwoord kunnen worden ingevoerd.

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

Queries op relaties
-------------------

Om object-relaties uit te lezen in WFS (momenteel niet ondersteund door MVT)
kun je de volgende optie toevoegen aan de URL:

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

Indien een tabel meerdere geometriëen bevat, zal deze voor ieder geometrieveld los opgenomen worden in de WFS.
Zodoende kunnen GIS-pakketten op beide geometrieën weergeven op de kaart.

Via MVT kan alleen de hoofdgeometrie (``mainGeometry``) van een dataset worden geladen.

Dit is bijvoorbeeld te zien bij Horeca-exploitatievergunningen: er wordt een aparte laag voor het pand,
en de bijbehorende terrassen beschikbaar gesteld. Zodoende kunnen beide geometriën uitgelezen worden.
De data van beide lagen is identiek; alleen de volgorde van geometrie-velden is aangepast.
