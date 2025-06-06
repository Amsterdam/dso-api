# Geometrie projecties

De geometrie velden worden standaard teruggegeven in de projectie van de
originele bron. Dit is veelal de rijksdriehoekscoördinaten (Amersfoort /
RD New). Met de `Accept-Crs` header kan opgegeven worden met welke
transformatie alle geometriewaarden teruggegeven moet worden.
Bijvoorbeeld:

``` bash
curl -H "Accept-Crs: EPSG:28992" https://api.data.amsterdam.nl/v1/gebieden/buurten/
```

Veelgebruikte projecties zijn:

| Projectie                     | Toelichting                                                                               |
|-------------------------------|-------------------------------------------------------------------------------------------|
| `urn:ogc:def:crs:EPSG::28992` | Nederlandse rijksdriehoekscoördinaten (RD New).                                           |
| `urn:ogc:def:crs:EPSG::4258`  | ETRS89, Europese projectie.                                                               |
| `urn:ogc:def:crs:EPSG::3857`  | Pseudo-Mercator (vergelijkbaar met Google Maps)                                           |
| `urn:ogc:def:crs:EPSG::4326`  | WGS 84 latitude/longitude, het wereldwijde GPS systeem. Coordinaten zijn in y/x volgorde. |
| `urn:ogc:def:crs:OGC::CRS84`  | WGS 84 longitude/latitude. Coordinaten zijn in x/y volgorde, o.a. gebruikt in GeoJSON.    |
| `EPSG:4326`                   | De oude notatie voor WGS 84, en geeft coordinaten in de oude longitude/latitude volgorde. |

De andere notatievormen (zoals `EPSG:4326` en `www.opengis.net` URI's) worden ook ondersteund.

<aside class="warning">
<h4 class="title">Let op</h4>
<p>
  Bij het gebruik van de <code>EPSG:4326</code> notatie,
  zullen de coordinaten wel in oude volgorde worden teruggegeven!
</p>
<p>
  Software die de aanbevolen notatie gebruikt,
  zoals <code>urn:ogc:def:crs:EPSG::4326</code>
  of <code>http://www.opengis.net/def/crs/epsg/0/4326</code> ontvangen de coordinaten in latitude/longitude.
</p>
</aside>

## De volgorde van coördinaten

Wanneer Nederlande rijksdriehoek coördinaten vertaald worden naar WGS 84,
komt dit per ongeluk soms in de **Arabische zee** terecht.

Dat betekend dat latitude van ±52 en longitude van ±4 omgedraaid zijn.
Dat heeft te maken met de assen-volgorde van de gekozen geometrieprojecties,
en wijze waarop brondata en de gekozen toepassing ingesteld zijn.

Veel computersystemen werken altijd in **x/y** schermposities.
De eerdere geo-standaarden deden dit ook.
Dergelijke volgordes zijn echter niet universeel, en dat geeft [veel verwarring](https://wiki.osgeo.org/wiki/Axis_Order_Confusion)
en is [niet consistent](https://macwright.com/lonlat/).
Bijvoorbeeld:

* Vraag je iemand van de marine/luchtverkeersvaart om een coördinaat,
  dan zul je een *latitude/longitude* (noord/west) krijgen - voor programmeurs gezien als **y/x**-volgorde.
* In geodesie (o.a. landmeetkunde) worden latitude/longitude zelfs als x/y behandeld.
* Kijk je vanuit astromomie, dan is '*afstand/hoogtegraad/breedtegraad*' een logische volgorde.
* In de dagelijke praktijk meten we verpakkingen in '*lengte x breedte x hoogte*',
  maar een serverchassis eerder in '*hoogte x breedte x diepte*'.
* Het meeste schrift is van links naar rechts, boven naar beneden opgesteld,
  maar ook dat is slechts een plaatselijke conventie.

Binnen de OGC standaarden is uiteindelijk gekozen om de assen-volgorde
van de authoriteit van de <abbr title="Coordinaat Referentie Systeem">CRS</abbr> aan te houden.
Een antwoord van een WFS 1.3 en 2.0 server zal deze volgorde aanhouden.

### Uitzonderingen.

Voor web-gebaseerde clients is de authoriteit-volgorde niet handig,
want dan moet iedere client een tabel met alle CRS'en bijhouden.
Daarom werkt GeoJSON altijd in x/y van `urn:ogc:def:crs:OGC::CRS84`,
ofwel longitude/latitude volgorde.

Ook is de <abbr title="Spatial Reference ID">SRID</abbr> 4326 dubbelzinnig,
en afhankelijk van de gekozen authoriteit.
In `urn:ogc:def:crs:EPSG::4326` levert dat **y/x** coordinaten op,
en bij `urn:ogc:def:crs:OGC::CRS84`
(ook <abbr title="Spatial Reference ID">SRID</abbr> 4326)
een **x/y** coordinaten volgorde. Wie nadrukkelijk die volgorde wil,
kan het beste `urn:ogc:def:crs:OGC::CRS84` gebruiken.

Om legacy software te ondersteunen, wordt bij de notatiewijze `EPSG:4326`
(en alleen bij deze code) de coordinaten in *longitude/latitude* (x/y) teruggegeven.

De onderliggende <abbr title="Geometry Engine, Open Source">GEOS</abbr>-bibliotheek
die PostgreSQL/PostGIS gebruikt heeft *geen* kennis van assenvolgorde.
PostGIS slaat de gegevens daarom altijd in x/y op samen met de numerieke SRID.
Wie met directe database toegang een SQL query uitvoert,
zal dit bij <abbr title="Spatial Reference ID">SRID</abbr> 4326 dus als *longitude/latitude* ontvangen.
