# Werken met QGIS

<aside class="tip">
<h4 class="title">Tip</h4>
Een overzicht van alle WFS API's is te vinden
op: <a href="/v1/wfs/">https://api.data.amsterdam.nl/v1/wfs/</a>.
</aside>

## Eenmalige lokale setup

Let op, een eenmalige setup van de qgis-auth.db in je locale profiel is
nodig voordat je de API endpoints toevoegt. Onthoudt jouw gebruikersnaam
en wachtwoord goed.

## WFS

De WFS-lagen zijn beschikbaar onder de volgende URL's:

`https://api.data.amsterdam.nl/v1/wfs/{<dataset>}/`

Gebruik zo'n URL in QGIS:

<img alt="Voorbeeldafbeelding van QGIS" src="/v1/static/images/qgis-add-wfs.png" style="width: 670px; height: 791px;">

In de bovenstaande afbeelding wordt QGIS gekoppeld met de BAG dataset:
[https://api.data.amsterdam.nl/v1/wfs/bag/](/v1/wfs/bag/)

<aside class="tip">
<h4 class="title">Tip</h4>

De parameters <code>?SERVICE=WFS&VERSION=2.0.0&REQUEST=..</code> worden door QGIS
zelf achter de URL gezet. Het is niet nodig deze zelf toe te voegen.
</aside>

<aside class="tip">
<h4 class="title">Tip</h4>

De schuine streep aan het einde van de URL is belangrijk. QGIS werkt
niet als deze ontbreekt. Dit is een beperking in QGIS.
</aside>

## Vector tiles (MVT)

QGis heeft geen ingebouwde ondersteuning voor TileJSON.
Deze is wel beschikbaar via de **MapTiler** plugin: https://plugins.qgis.org/plugins/tags/tilejson/.
Vervolgens kan je de TileJSON inladen:

  - `https://api.data.amsterdam.nl/v1/mvt/<dataset>/tilejson.json`.

De standaard QGis functionaliteit vereist dat je handmatig
een "X/Y/Z-tegel" of "Vectortegel" URL opgeeft:

  - In de *Browser* (linker tabblad), rechtermuisklik op *Vector Tiles*,
    dan *Nieuwe algemene verbinding* (*New Generic Connection*).
  - De URL is
    `https://api.data.amsterdam.nl/v1/mvt/<dataset>/<tabel>/{z}/{x}/{y}.pbf`.
    Vervang `<dataset>` en `<tabel>` door de namen in kwestie, maar laat
    `{z}/{x}/{y}` staan, inclusief de accolades.
  - *Min. zoomniveau* (*Min. Zoom Level*) staat standaard op 0. Zet dit op 1.

Een lijst van datasets die vector tiles ondersteunen is beschikbaar op:
[https://api.data.amsterdam.nl/v1/mvt/](/v1/mvt/).

## Autorisatie

Voor gesloten datasets moet ook een autorisatieconfiguratie worden
toegevoegd. Dit kan door op het groene kruisje in het bovenstaande menu
te klikken. Selecteer OAuth2-authenticatie, met 'implicit' grant flow.
Vul bij 'request url'
`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/auth`
en bij 'token url'
`https://iam.amsterdam.nl/auth/realms/datapunt-ad/protocol/openid-connect/certs`
in. De client id is `qgis`, Scope is `email` en access method is
`header`. QGIS zal bij het activeren van een kaartlaag een browserscherm
openen, waarin gebruikersnaam en wachtwoord kunnen worden ingevoerd.

**Voor acceptatie vervang je in bovengenoemde URLs "datapunt-ad" met
"datapunt-ad-acc"**.

<img alt="Voorbeeldafbeelding van QGIS-authenticatie"
 src="/v1/static/images/qgis-add-authentication.png"
 style="width: 670px; height: 791px;">

In de bovenstaande afbeelding wordt authenticatieconfiguratie
ingevoerd in QGIS.

Hierna zijn de gegevens te raadplegen, te filteren en te combineren:

<img src="/v1/static/images/qgis-bag.png" width="2438" height="1614"
 style="width: 609.5px; height: 403.5px;"
 alt="Stadsdelen weergegeven in QGIS"/>

## Queries op relaties

Om object-relaties uit te lezen in WFS (momenteel niet ondersteund door
MVT) kun je de volgende optie toevoegen aan de URL:

  - `?embed={relatienaam},{...}` zal een veld platgeslagen invoegen.
  - `?expand={relatienaam},{...}` zal een veld als "complex feature"
    invoegen.

Gebruik deze URL in QGIS, of een ander GIS-pakket.

Als voorbeeld: de BAG feature type *buurt* een relatie met een
*stadsdeel*. Deze kan op beide manieren geconfigureerd worden in een
GIS-pakket:

  - `https://api.data.amsterdam.nl/v1/wfs/bag/?embed=stadsdeel` levert
    een [stadsdelen met platgeslagen dot-notate](/v1/wfs/bag/?embed=stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=buurt&COUNT=5).
  - `https://api.data.amsterdam.nl/v1/wfs/bag/?expand=stadsdeel` levert
    een [stadsdelen als complex feature](/v1/wfs/bag/?expand=stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=buurt&COUNT=5).

Deze parameters kunnen gecombineerd worden met de `OUTPUTFORMAT`
parameter, zodat het export formaat ook geneste relaties bevat.

<aside class="admonition">
<h4 class="title">Embed of expand gebruiken?</h4>

QGIS 3 heeft geen ondersteuning voor complex features, en verwerkt deze
als tekst. Gebruikt in QGIS daarom alleen de platgeslagen versie met
`?embed={...}`. De `?expand={...}` versie is daarentegen ideaal voor
GeoJSON exports, die wel goed kan omgaan met geneste structuren.
</aside>

## Datasets met meerdere geometrieën

Indien een tabel meerdere geometriëen bevat, zal deze voor ieder
geometrieveld los opgenomen worden in de WFS. Zodoende kunnen
GIS-pakketten op beide geometrieën weergeven op de kaart.

Via MVT kan alleen de hoofdgeometrie (`mainGeometry`) van een dataset
worden geladen.

Dit is bijvoorbeeld te zien bij Horeca-exploitatievergunningen: er wordt
een aparte laag voor het pand, en de bijbehorende terrassen beschikbaar
gesteld. Zodoende kunnen beide geometriën uitgelezen worden. De data van
beide lagen is identiek; alleen de volgorde van geometrie-velden is
aangepast.
