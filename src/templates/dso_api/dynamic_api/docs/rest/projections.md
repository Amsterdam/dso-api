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

| Projectie    | Toelichting                                     |
| ------------ | ----------------------------------------------- |
| `EPSG:28992` | Nederlandse rijksdriehoekscoördinaten (RD New). |
| `EPSG:4258`  | ETRS89, Europese projectie.                     |
| `EPSG:3857`  | Pseudo-Mercator (vergelijkbaar met Google Maps) |
| `EPSG:4326`  | WGS 84 latitude-longitude, wereldwijd.          |

De andere notatievormen (zoals `urn:ogc:def:crs:EPSG::4326` en
`www.opengis.net` URI's) worden ook ondersteund.
