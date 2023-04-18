# WFS handmatig koppelen

De WFS server kan rechtstreeks vanuit de browser of HTTP-client (curl
e.d.) uitgelezen worden. Gebruik de basis URL
`https://api.data.amsterdam.nl/v1/wfs/{<dataset naam>}/` in een
WFS-client.

Voor HTTP-clients voeg je
`?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES={laagnaam}`
toe. De parameters `?expand` en `?embed`
([elders beschreven](../rest/embeds.html)) werken ook.

## Exportformats

De volgende exportformats zijn beschikbaar:

  - GeoJSON
  - CSV

Deze worden opgevraagd door zelf een **GetFeature** aanvraag samen te
stellen. Hiervoor zijn de parameters `TYPENAMES={laagnaam}` en
`OUTPUTFORMAT={format}` nodig. De volledige URL wordt dan:

`https://api.data.amsterdam.nl/v1/wfs/{dataset}/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES={laagnaam}&OUTPUTFORMAT={format}`.

Bijvoorbeeld:

  - [...&TYPENAMES=wijken&OUTPUTFORMAT=geojson](https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson)
  - [...&TYPENAMES=wijken&OUTPUTFORMAT=csv](https://api.data.amsterdam.nl/v1/wfs/gebieden/?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=csv)

<div class="tip">

<div class="title">

Tip

</div>

In de bovenstaande links is een `COUNT=` parameter opgenomen, die
paginering activeert. Door deze parameter weg te laten worden *alle
objecten* in een enkele request opgehaald. De server kan voor de meeste
datasets dit met een goede performance leveren.

</div>

## Relaties bij exportformats

De exportformats ondersteunen tevens het embedden/nesten van relaties.
Hiervoor is het voldoende om de nesting-parameters te gebruiken bij het
export links.

Bijvoorbeeld:

  - [?embed=ligt\_in\_stadsdeel&...&TYPENAMES=wijken&OUTPUTFORMAT=geojson](https://api.data.amsterdam.nl/v1/wfs/gebieden/?embed=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson)
  - [?expand=ligt\_in\_stadsdeel&...&TYPENAMES=wijken&OUTPUTFORMAT=geojson](https://api.data.amsterdam.nl/v1/wfs/gebieden/?expand=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson)
  - [?embed=ligt\_in\_stadsdeel&...&TYPENAMES=wijken&OUTPUTFORMAT=csv](https://api.data.amsterdam.nl/v1/wfs/gebieden/?embed=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=csv)
  - [?expand=ligt\_in\_stadsdeel&...&TYPENAMES=wijken&OUTPUTFORMAT=csv](https://api.data.amsterdam.nl/v1/wfs/gebieden/?expand=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=csv)

<div class="admonition">

Sommige formats hebben beperkingen.

De CSV-export kan alleen complexe relaties verwerken als deze ook
platgeslagen kunnen worden. Dit is een beperking van het format zelf.

</div>

## Geometrie projectie

De exportlink kan uitgebreid worden met de `SRSNAME` parameter om
geometrie velden in de gewenste projectie te ontvangen. Bijvoorbeeld:
`SRSNAME=urn:ogc:def:crs:EPSG::3857` voor de web-mercator projectie die
Google Maps gebruikt. De toegestane projecties zijn:

| Projectie                     | Toelichting                                     |
| ----------------------------- | ----------------------------------------------- |
| `urn:ogc:def:crs:EPSG::28992` | Nederlandse rijksdriehoekscoördinaten (RD New). |
| `urn:ogc:def:crs:EPSG::4258`  | ETRS89, Europese projectie.                     |
| `urn:ogc:def:crs:EPSG::3857`  | Pseudo-Mercator (vergelijkbaar met Google Maps) |
| `urn:ogc:def:crs:EPSG::4326`  | WGS 84 longitude-latitude, wereldwijd.          |

## Eenvoudige Filters

Het WFS-protocol biedt een krachtige syntax voor het filteren van data.
Gebruik hiervoor `REQUEST=GetFeature` en het `FILTER` argument, waarbij
de waarde als XML wordt uitgedrukt:

``` xml
<Filter>
    <PropertyIsEqualTo>
        <ValueReference>ligt_in_stadsdeel/naam</ValueReference>
        <Literal>Centrum</Literal>
    </PropertyIsEqualTo>
</Filter>
```

Dit wordt dan in de request verwerkt, bijvoorbeeld:

  - [...&TYPENAMES=wijken&OUTPUTFORMAT=geojson&FILTER=%3CFilter%3E%3CPropertyIsEqualTo%3E%3CValueReference...](https://api.data.amsterdam.nl/v1/wfs/gebieden/?expand=ligt_in_stadsdeel&SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=wijken&COUNT=10&OUTPUTFORMAT=geojson&FILTER=%3CFilter%3E%3CPropertyIsEqualTo%3E%3CValueReference%3Eligt_in_stadsdeel/naam%3C/ValueReference%3E%3CLiteral%3ECentrum%3C/Literal%3E%3C/PropertyIsEqualTo%3E%3C/Filter%3E)

De `FILTER` parameter vervangt de losse parameters `BBOX` en
`RESOURCEID`. Als je deze parameters ook gebruikt, moet je deze opnemen
in het filter:

``` xml
<Filter>
    <And>
        <BBOX>
            <gml:Envelope srsName="EPSG:4326">
                <gml:lowerCorner>4.58565 52.03560</gml:lowerCorner>
                <gml:upperCorner>5.31360 52.48769</gml:upperCorner>
            </gml:Envelope>
        </BBOX>
        <PropertyIsEqualTo>
            <ValueReference>status</ValueReference>
            <Literal>1</Literal>
        </PropertyIsEqualTo>
    </And>
</Filter>
```

De `RESOURCEID` kan in het filter meermaals voorkomen:

``` xml
<Filter>
    <ResourceId rid="TYPENAME.123" />
    <ResourceId rid="TYPENAME.4325" />
    <ResourceId rid="OTHERTYPE.567" />
</Filter>
```

## Complexe filters

De WFS Filter Encoding Standaard (FES) ondersteunt veel operatoren. Deze
tags worden allemaal ondersteund:

| Element                            | SQL equivalent            | Omschrijving                                                                                      |
| ---------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------- |
| `<PropertyIsEqualTo>`              | `{a} == {b}`              | Exacte waarde vergelijken tussen 2 expressies.                                                    |
| `<PropertyIsNotEqualTo>`           | `{a} != {b}`              | Waarde moet ongelijk zijn.                                                                        |
| `<PropertyIsLessThan>`             | `{a} < {b}`               | Waarde 1 moet kleiner zijn dan waarde 2.                                                          |
| `<PropertyIsGreaterThan>`          | `{a} > {b}`               | Waarde 1 moet groter zijn dan waarde 2.                                                           |
| `<PropertyIsLessThanOrEqualTo>`    | `{a} <= {b}`              | Waarde 1 moet kleiner of gelijk zijn dan waarde 2.                                                |
| `<PropertyIsGreaterThanOrEqualTo>` | `{a} >= {b}`              | Waarde 1 moet groter of gelijk zijn dan waarde 2.                                                 |
| `<PropertyIsBetween>`              | `{a} BETWEEN {x} AND {y}` | Vergelijkt tussen `<LowerBoundary>` en `<UpperBoundary>`, die beiden een expressie bevatten.      |
| `<PropertyIsLike>`                 | `{a} LIKE {b}`            | Voert een wildcard vergelijking uit.                                                              |
| `<PropertyIsNil>`                  | `{a} IS NULL`             | Waarde moet `NULL` zijn (`xsi:nil="true"` in XML).                                                |
| `<PropertyIsNull>`                 | n.b.                      | Property mag niet bestaan (momenteel identiek aan `<PropertyIsNil>` geïmplementeerd).             |
| `<BBOX>`                           | `ST_Intersects({a}, {b})` | Geometrie moet in waarde 2 voorkomen. De veldnaam mag weggelaten worden.                          |
| `<Contains>`                       | `ST_Contains({a}, {b})`   | Geometrie 1 bevat geometrie 2 compleet.                                                           |
| `<Crosses>`                        | `ST_Crosses({a}, {b})`    | Geometrieën lopen door elkaar heen.                                                               |
| `<Disjoint>`                       | `ST_Disjoint({a}, {b})`   | Geometrieën zijn niet verbonden.                                                                  |
| `<Equals>`                         | `ST_Equals({a}, {b})`     | Geometrieën moeten gelijk zijn.                                                                   |
| `<Intersects>`                     | `ST_Intersects({a}, {b})` | Geometrieën zitten in dezelfde ruimte.                                                            |
| `<Touches>`                        | `ST_Touches({a}, {b})`    | Randen van de geometrieën raken elkaar.                                                           |
| `<Overlaps>`                       | `ST_Overlaps({a}, {b})`   | Geometrie 1 en 2 overlappen elkaar.                                                               |
| `<Within>`                         | `ST_Within({a}, {b})`     | Geometrie 1 ligt compleet in geometrie 2.                                                         |
| `<And>`                            | `{a} AND {b}`             | De geneste elementen moeten allemaal waar zijn.                                                   |
| `<Or>`                             | `{a} OR {b}`              | Slechts één van de geneste elementen hoeft waar zijn.                                             |
| `<Not>`                            | `NOT {a}`                 | Negatie van het geneste element.                                                                  |
| `<ResourceId>`                     | `table.id == {value}`     | Zoekt slechts een enkel element op "typenaam.identifier". Meerdere combineren tot een `IN` query. |

<div class="tip">

<div class="title">

Tip

</div>

Bij de operator `<BBOX>` mag het geometrieveld weggelaten worden. Het
standaardgeometrieveld wordt dan gebruikt (doorgaans het eerste veld).

</div>

<div class="note">

<div class="title">

Note

</div>

Hoewel een aantal geometrie-operatoren dubbelop lijken voor vlakken
(zoals `<Intersects>`, `<Crosses>` en `<Overlaps>`), worden de
onderlinge verschillen met name zichtbaar bij het vergelijken van punten
met vlakken.

</div>

Als waarde mogen diverse expressies gebruikt worden:

| Expressie          | SQL equivalent      | Omschrijving                                              |
| ------------------ | ------------------- | --------------------------------------------------------- |
| `<ValueReference>` | `{veldnaam}`        | Verwijzing naar een veld.                                 |
| `<Literal>`        | waarde              | Letterlijke waarde, mag ook een GML-object zijn.          |
| `<Function>`       | `{functienaam}(..)` | Uitvoer van een functie, zoals `abs`, `sin`, `strLength`. |
| `<Add>`            | `{a} + {b}`         | Waarden optellen (WFS 1 expressie).                       |
| `<Sub>`            | `{a} - {b}`         | Waarden aftrekken (WFS 1 expressie).                      |
| `<Mul>`            | `{a} * {b}`         | Waarden ermenigvuldigen (WFS 1 expressie).                |
| `<Div>`            | `{a} / {b}`         | Waarden delen (WFS 1 expressie).                          |

Dit maakt complexe filters mogelijk, bijvoorbeeld:

``` xml
<Filter>
    <And>
        <PropertyIsEqualTo>
            <ValueReference>status</ValueReference>
            <Literal>1</Literal>
        </PropertyIsEqualTo>
        <Or>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Rest</Literal>
            </PropertyIsEqualTo>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Textiel</Literal>
            </PropertyIsEqualTo>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Glas</Literal>
            </PropertyIsEqualTo>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Papier</Literal>
            </PropertyIsEqualTo>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Gft</Literal>
            </PropertyIsEqualTo>
            <PropertyIsEqualTo>
                <ValueReference>fractie_omschrijving</ValueReference>
                <Literal>Plastic</Literal>
            </PropertyIsEqualTo>
        </Or>
    </And>
</Filter>
```

## Functies

Functies worden uitgevoerd door met de tag `<Function
name="..">..</Function>`. Dit mag op iedere plek als expressie gebruikt
worden in plaats van een `<ValueReference>` of `<Literal>`.

Binnen in de function worden de parameters tevens als expressie
opgegeven: een `<ValueReference>`, `<Literal>` of nieuwe `<Function>`.
Als simpel voorbeeld:

``` xml
<fes:Function name="sin">
    <fes:ValueReference>fieldname</fes:ValueReference>
</fes:Function>
```

De volgende functies zijn beschikbaar in de server:

| Functie                              | SQL equivalent               | Omschrijving                                               |
| ------------------------------------ | ---------------------------- | ---------------------------------------------------------- |
| `strConcat(string)`                  | `CONCAT()`                   | Combineert teksten                                         |
| `strToLowerCase(string)`             | `LOWER()`                    | Tekst omzetten naar kleine letters.                        |
| `strToUpperCase(string)`             | `UPPER()`                    | Tekst omzetten naar hoofdletters                           |
| `strTrim(string)`                    | `TRIM()`                     | Witruimte aan het begin en einde verwijderen.              |
| `strLength(string)`                  | `LENGTH()` / `CHAR_LENGTH()` | Tekstlengte bepalen.                                       |
| `length(string)`                     | `LENGTH()` / `CHAR_LENGTH()` | Alias van `strLength()`.                                   |
| `abs(number)`                        | `ABS()`                      | Negatieve getallen omdraaien.                              |
| `ceil(number)`                       | `CEIL()`                     | Afronden naar boven.                                       |
| `floor(number)`                      | `FLOOR()`                    | Afronden naar beneden.                                     |
| `round(value)`                       | `ROUND()`                    | Afronden                                                   |
| `min(value1, value2)`                | `LEAST()`                    | Kleinste getal gebruiken.                                  |
| `max(value1, value2)`                | `GREATEST()`                 | Grootste getal gebruiken.                                  |
| `pow(base, exponent)`                | `POWER()`                    | Machtsverheffing                                           |
| `exp(value)`                         | `EXP()`                      | Exponent van 𝑒 (2,71828...; natuurlijke logaritme).        |
| `log(value)`                         | `LOG()`                      | Logaritme; inverse van een exponent.                       |
| `sqrt(value)`                        | `SQRT()`                     | Worteltrekken; inverse van machtsverheffen.                |
| `acos(value)`                        | `ACOS()`                     | Arccosinus; inverse van cosinus.                           |
| `asin(value)`                        | `ASIN()`                     | Arcsinus; inverse van sinus.                               |
| `atan(value)`                        | `ATAN()`                     | Arctangens; invere van tangens.                            |
| `atan2(x, y)`                        | `ATAN2()`                    | Arctangens, voor bereik buiten een circel.                 |
| `cos(radians)`                       | `COS()`                      | Cosinus                                                    |
| `sin(radians)`                       | `SIN()`                      | Sinus                                                      |
| `tan(radians)`                       | `TAN()`                      | Tangens                                                    |
| `pi()`                               | `PI`                         | De waarde van π (3,141592653...)                           |
| `toDegrees(radians)`                 | `DEGREES()`                  | Omzetting radialen naar graden.                            |
| `toRadians(degree)`                  | `RADIANS()`                  | Omzetting graden naar radialen.                            |
| `Area(geometry)`                     | `ST_AREA()`                  | Geometrie omzetten naar gebied.                            |
| `Centroid(features)`                 | `ST_Centroid()`              | Geometrisch centrum als "zwaartekrachtpunt" teruggeven.    |
| `Difference(geometry1, geometry2)`   | `ST_Difference()`            | Delen van geometrie 1 die niet overlappen met geometrie 2. |
| `distance(geometry1, geometry2)`     | `ST_Distance()`              | Minimale afstand tussen 2 geometrieën.                     |
| `Envelope(geometry)`                 | `ST_Envelope()`              | Geometrie omzetten naar bounding box.                      |
| `Intersection(geometry1, geometry2)` | `ST_Intersection()`          | Delen van geometrie 1 die overlappen met geometrie 2.      |
| `Union(geometry1, geometry2)`        | `ST_Union()`                 | Geometrie 1 en 2 samenvoegen.                              |

## Filter compatibiliteit

Officieel zijn XML-namespaces verplicht in het filter. Aangezien veel
clients deze achterwege laten, ondersteunt de server ook aanvragen
zonder namespaces. Voor de volledigheid zal het request er met
namespaces zo uit zien:

``` xml
<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.opengis.net/fes/2.0
        http://schemas.opengis.net/filter/2.0/filterAll.xsd">
    <fes:PropertyIsEqualTo>
        <fes:ValueReference>stadsdeel/naam</fes:ValueReference>
        <fes:Literal>Centrum</fes:Literal>
    </fes:PropertyIsEqualTo>
</fes:Filter>
```

Bij geometriefilters is dat officieel zelfs:

``` xml
<fes:Filter
    xmlns:fes="http://www.opengis.net/fes/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/fes/2.0
    http://schemas.opengis.net/filter/2.0/filterAll.xsd
    http://www.opengis.net/gml/3.2 http://schemas.opengis.net/gml/3.2.1/gml.xsd">
    <fes:BBOX>
        <gml:Polygon gml:id="P1" srsName="http://www.opengis.net/def/crs/epsg/0/4326">
            <gml:exterior>
                <gml:LinearRing>
                    <gml:posList>10 10 20 20 30 30 40 40 10 10</gml:posList>
                </gml:LinearRing>
            </gml:exterior>
        </gml:Polygon>
    </fes:BBOX>
</fes:Filter>
```

Conform de XML-regels mag hier de "fes" namespace alias hernoemd worden,
of weggelaten worden als er alleen `xmlns="..."` gebruikt wordt i.p.v.
`xmlns:fes="..."`.

Diverse bestaande filters gebruiken nog andere WFS 1-elementen, zoals
`<PropertyName>` in plaats van `<ValueReference>`. Voor compatibiliteit
wordt deze tag ook ondersteund.

De WFS 1-expressies `<Add>`, `<Sub>`, `<Mul>` en `<Div>` zijn tevens
geïmplementeerd om rekenkundige operaties te ondersteunen vanuit QGIS
(optellen, aftrekken, vermenigvuldigen en delen).
