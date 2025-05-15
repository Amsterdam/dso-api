# Paginering

De REST API geeft de resultaten gepagineerd terug. De paginagrootte kan
aangepast worden door een `?_pageSize={n}` query parameter toe te voegen
aan de request URL.

In de response zijn de volgende elementen te vinden:

``` javascript
{
    "_links": {
        "self": {
            "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/"
        },
        "next": {
            "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/?page=3"
        },
        "previous": {
            "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/?page=1"
        }
    },
    "_embedded": {

       // alle objecten...

    },
    "page": {
        "number": 2,
        "size": 20
    }
}
```

<aside class="note">
<h4 class="title">Note</h4>

In plaats van `_pageSize` wordt ook `page_size` ondersteund, maar
`_pageSize` heeft de voorkeur.
</aside>

Met de velden `_links.next` en `_links.previous` zijn respectievelijk de
volgende en vorige pagina op te vragen. Meer algemeen kan pagina
<span class="title-ref">n</span> worden opgevraagd met `?page={n}`.
Paginanummers beginnen bij één, niet nul. De links `next` en `previous`
ontbreken op de laatste, resp. eerste, pagina.

In het object `page` zijn de volgende velden opgenomen:

  - `page.number`: het huidige paginanummer;
  - `page.size`: de grootte van een pagina.

Wordt `?_count=true` meegegeven, dat bevat het tevens:

  - `page.totalElements`: het aantal objecten in de (gefilterde)
    resultaatset;
  - `page.totalPages`: het aantal pagina's dat de resultaatset beslaat.

Bijvoorbeeld:

``` javascript
"page": {
    "number": 1,
    "size": 20,
    "totalElements": 117,
    "totalPages": 6,
}
```

Het tellen van resultaten moet expliciet aangevraagd worden omdat dit
bij grote datasets vertragend werkt. Lees
<span class="title-ref">\_links.next</span> uit om te zien of er een
volgende pagina is.

De velden uit het `page`-object worden ook als HTTP-headers in de
response teruggegeven:

  - `X-Pagination-Page`: Het huidige paginanummer.
  - `X-Pagination-Limit`: de grootte van een pagina.
  - `X-Total-Count`: de grootte van de resultaatset.
  - `X-Pagination-Count`: het aantal paginas voor de gegeven
    `_pageSize`.

De laatste twee zijn weer alleen aanwezig in het geval `_count=true`.
