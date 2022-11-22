# Technische achtergrond

## Technische implementatie

De WFS server is gebouwd op basis van
[django-gisserver](https://django-gisserver.readthedocs.io). Deze Django
module ondersteunt het "Basic WFS" conformance level, en is getest op
compatibiliteit met de [CITE Teamengine Test
Suite](https://cite.opengeospatial.org/teamengine/).

## Beveiliging

De ingeladen features kunnen verschillen per gebruiker. De "feature
type" die de server intern opbouwd bevat alleen de attributen waar een
gebruiker toegang toe heeft. Het is daardoor niet mogelijk om te
filteren op afgeschermde velden, simpelweg omdat de server deze velden
niet herkent.

## Embedding

De XML uitvoer van de WFS server verschilt bij het gebruik van
`?embed={relatienaam},{...}` en `?expand={relatienaam},{...}`.

Deze embed logica is een uitbreiding op
[django-gisserver](https://django-gisserver.readthedocs.io). Door het
gebruik van `?embed` en `?expand` wordt er een andere feature-definitie
geactiveerd in de server, die een geneste structuur oplevert. Hierdoor
veranderd het gedrag en uitvoer van de server.

Bij een platgeslagen relatie worden alle veldnamen met een punt erin
opgebouwd:

``` xml
<app:buurt gml:id="buurt.03630000000078">
    <gml:name>00a</gml:name>
    <app:id>03630000000078</app:id>
    <app:code>00a</app:code>
    <app:naam>Kop Zeedijk</app:naam>
    <app:vollcode>A00a</app:vollcode>
    <app:geometrie>...
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::28992" gml:id="buurt.03630000000078.1">
            ...
        </gml:Polygon>
    </app:geometrie>
    <app:stadsdeel.id>03630000000018</app:stadsdeel.id>
    <app:stadsdeel.code>A</app:stadsdeel.code>
    <app:stadsdeel.naam>Centrum</app:stadsdeel.naam>
    <app:stadsdeel.vervallen xsi:nil="true" />
    <app:stadsdeel.date_modified>2020-07-28T22:25:24.197978+00:00</app:stadsdeel.date_modified>
    <app:stadsdeel.ingang_cyclus>2015-01-01</app:stadsdeel.ingang_cyclus>
    <app:stadsdeel.begin_geldigheid>2015-01-01</app:stadsdeel.begin_geldigheid>
    <app:stadsdeel.einde_geldigheid xsi:nil="true" />
    <app:stadsdeel.brondocument_naam>3B/2015/134</app:stadsdeel.brondocument_naam>
    <app:stadsdeel.brondocument_datum>2015-06-23</app:stadsdeel.brondocument_datum>
    <app:stadsdeel_id>03630000000018</app:stadsdeel_id>
    <app:vervallen xsi:nil="true" />
    <app:date_modified>2020-07-28T22:25:32.261814+00:00</app:date_modified>
    <app:ingang_cyclus>2006-06-12</app:ingang_cyclus>
    <app:begin_geldigheid>2006-06-12</app:begin_geldigheid>
    <app:buurtcombinatie_id>3630012052036</app:buurtcombinatie_id>
    <app:einde_geldigheid xsi:nil="true" />
    <app:brondocument_naam />
    <app:brondocument_datum xsi:nil="true" />
    <app:gebiedsgerichtwerken_id>DX01</app:gebiedsgerichtwerken_id>
</app:buurt>
```

Bij een "complex feature" gebruikt de XML uitvoer een eigen
`<app:stadsdeel>` object:

``` xml
<app:buurt gml:id="buurt.03630000000078">
    <gml:name>00a</gml:name>
    <app:id>03630000000078</app:id>
    <app:code>00a</app:code>
    <app:naam>Kop Zeedijk</app:naam>
    <app:vollcode>A00a</app:vollcode>
    <app:geometrie>...
        <gml:Polygon srsName="urn:ogc:def:crs:EPSG::28992" gml:id="buurt.03630000000078.1">
            ...
        </gml:Polygon>
    </app:geometrie>
    <app:stadsdeel>
        <app:id>03630000000018</app:id>
        <app:code>A</app:code>
        <app:naam>Centrum</app:naam>
        <app:vervallen xsi:nil="true" />
        <app:date_modified>2020-07-28T22:25:24.197978+00:00</app:date_modified>
        <app:ingang_cyclus>2015-01-01</app:ingang_cyclus>
        <app:begin_geldigheid>2015-01-01</app:begin_geldigheid>
        <app:einde_geldigheid xsi:nil="true" />
        <app:brondocument_naam>3B/2015/134</app:brondocument_naam>
        <app:brondocument_datum>2015-06-23</app:brondocument_datum>
    </app:stadsdeel>
    <app:stadsdeel_id>03630000000018</app:stadsdeel_id>
    <app:vervallen xsi:nil="true" />
    <app:date_modified>2020-07-28T22:25:32.261814+00:00</app:date_modified>
    <app:ingang_cyclus>2006-06-12</app:ingang_cyclus>
    <app:begin_geldigheid>2006-06-12</app:begin_geldigheid>
    <app:buurtcombinatie_id>3630012052036</app:buurtcombinatie_id>
    <app:einde_geldigheid xsi:nil="true" />
    <app:brondocument_naam></app:brondocument_naam>
    <app:brondocument_datum xsi:nil="true" />
    <app:gebiedsgerichtwerken_id>DX01</app:gebiedsgerichtwerken_id>
</app:buurt>
```
