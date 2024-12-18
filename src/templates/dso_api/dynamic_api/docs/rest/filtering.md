# Filtering

## Filteren op attributen

Ieder veld kan gebruikt worden om op te filteren. Bijvoorbeeld:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam=Westpoort'
```

Als het veld een array van objecten is, kunnen de subvelden van de
objecten gefilterd worden met de naam van de array en de naam van het
subveld gescheiden door een punt. Voorbeeld: het veld

``` json
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
```

kan gefilterd worden met:

``` bash
curl 'https://api.data.amsterdam.nl/v1/bag/verblijfsobjecten/?gebruiksdoel.code=1'
```

## Filteren in relaties

De relaties, en attributen van relaties, kunnen gebruikt worden in
filters. Verbind de velden door middel van een punt-notatie
(`relatie.veldnaam`).

Bijvoorbeeld bij een enkelvoudige relatie:

``` bash
curl 'https://api.data.amsterdam.nl/v1/huishoudelijkafval/container/?locatie.id=10009'
```

...een temporele relatie:

``` bash
curl 'https://api.data.amsterdam.nl/v1/bag/verblijfsobjecten/?heeftHoofdadres.identificatie=0363200000006110&heeftHoofdadres.volgnummer=1'
```

...of een relatie zonder volgnummer, die altijd verwijst naar het
laatste voorkomen:

``` bash
curl 'http://api.data.amsterdam.nl/v1/huishoudelijkafval/container/?locatie.gbdBuurt.identificatie=03630000000770'
```

Je kan ieder ander veld uit de relatie ook gebruiken, zoals bijvoorbeeld
`?locatie.status=0` of een genest veld:
`?locatie.gbdBuurt.identificatie=...`. Deze opties staan niet in het
naslagwerk vermeld, maar kunnen wel samengesteld worden door de velden
van de API of documentatie te combineren. Het zoeken op de identificatie
(primaire sleutel) is het snelste, en de beste keuze als je de
identificatie ook weet.

## Operatoren

Afhankelijk van het veldtype zijn er extra operatoren mogelijk.

<div class="tip">

<div class="title">

Tip

</div>

De exacte namen en mogelijke velden per tabel zijn op de `REST API
Datasets <../datasets/index>` pagina te zien.

</div>

### Voor alle veldtypes

| Operator                | Werking                                | SQL Equivalent         |
| ----------------------- | -------------------------------------- | ---------------------- |
| `?{veld}[in]={x},{y}`   | De waarde moet één van de opties zijn. | `{veld} IN ({x}, {y})` |
| `?{veld}[not]={x}`      | De waarde moet niet voorkomen.         | `{veld} != {x}`.       |
| `?{veld}[isnull]=true`  | Het veld mag niet ingevuld zijn.       | `{veld} IS NULL`       |
| `?{veld}[isnull]=false` | Het veld moet ingevuld zijn.           | `{veld} IS NOT NULL`   |

### Bij waarden met getallen

| Operator           | Werking                                                          | SQL Equivalent  |
| ------------------ | ---------------------------------------------------------------- | --------------- |
| `?{veld}[lt]={x}`  | Test op kleiner dan (lt=Less Then)                               | `{veld} < {x}`  |
| `?{veld}[lte]={x}` | Test op kleiner dan of gelijk (lte: less then or equal to)"      | `{veld} <= {x}` |
| `?{veld}[gt]={x}`  | Test op groter dan (gt=greater then)                             | `{veld} > {x}`  |
| `?{veld}[gte]={x}` | Test op groter dan of gelijk aan (gte: greater then or equal to) | `{veld} >= {x}` |

### Bij waarden met tekst

| Operator                      | Werking                                              | SQL Equivalent                        |
| ----------------------------- | ---------------------------------------------------- | ------------------------------------- |
| `?{tekstveld}[like]={x}`      | Zoekt in tekstgedeelte met jokertekens (`*` en `?`). | `{tekstveld} LIKE '{x}'`              |
| `?{tekstveld}[isempty]=true`  | Waarde moet leeg zijn                                | `{veld} IS NULL OR {veld} = ''`       |
| `?{tekstveld}[isempty]=false` | Waarde mag niet niet leeg zijn                       | `{veld} IS NOT NULL AND {veld} != ''` |

De `like`-operator maakt *fuzzy search* met jokertekens (*wildcards*)
mogelijk. Het teken `*` staat voor nul of meer willekeurige tekens, `?`
staat voor precies één willekeurig teken. Alle andere tekens staan voor
zichzelf. Bijvoorbeeld:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=West*'

curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?naam[like]=??st'
```

`naam[like]=West*` selecteert alle rijen in een dataset waarvan de naam
begint met "West", inclusief stadsdeel West. Rijen waarvan de naam
"West" *bevat* kunnen gevonden worden met `*West*`. De zoekterm `??st`
selecteert "Oost" en "West": twee willekeurige tekens, gevolgd door
"st".

Als de filtertekst geen jokertekens bevat gedraagt `like` zich hetzelfde
als `exact`. Er is geen *escaping* van de jokertekens mogelijk.

### Bij waarden met lijsten

| Operator                         | Werking                       | SQL Equivalent              |
| -------------------------------- | ----------------------------- | --------------------------- |
| `?{arrayveld}[contains]={x},{y}` | De lijst moet beide bevatten. | `({x}, {y}) IN {arrayveld}` |

### Bij waarden met een geometrie

| Operator                                            | Werking                                                | SQL Equivalent                                       |
| --------------------------------------------------- | ------------------------------------------------------ | -----------------------------------------------------|
| `?{geoveld}[contains]={x},{y}`                      | Geometrie moet voorkomen op een punt (intersectie)     | `ST_Intersects({geoveld}, POINT({x} {y}))`           |
| `?{geoveld}[contains]=POINT(x y)`                   | Idem, nu in de WKT (well-known text) notatie.          | `ST_Intersects({geoveld}, POINT({x} {y}))`           |
| `?{geoveld}[intersects]={x},{y}`                    | Geometrie moet voorkomen op een punt (intersectie)     | `ST_Intersects({geoveld}, POINT({x} {y}))`           |
| `?{geoveld}[intersects]=POINT(x y)`                 | Idem, nu in de WKT (well-known text) notatie.          | `ST_Intersects({geoveld}, POINT({x} {y}))`           |
| `?{geoveld}[intersects]=POLYGON ((4.89...))`        | Geometry moet overlappen met een polygon (intersectie).| `ST_Intersects({geoveld}, POLYGON ((4.89...)))`      |
| `?{geoveld}[intersects]=MULTIPOLYGON (((4.89...)))` | Geometry moet overlappen met een MULTIPOLYGON          | `ST_Intersects({geoveld}, MULTIPOLYGON ((4.89...)))` |

Bij het doorzoeken van geometrievelden wordt gebruik gemaakt van de
projectie opgegeven in de header `Accept-CRS`. Afhankelijk van de
projectie wordt x,y geïnterpreteerd als longitude, latitude of x,y in RD
of anderszins. Indien `Accept-CRS` niet wordt meegegeven worden x en y,
afhankelijk van de waardes, geinterpreteerd als longitude en latitude in
`EPSG:4326` of `EPSG:28992`.
