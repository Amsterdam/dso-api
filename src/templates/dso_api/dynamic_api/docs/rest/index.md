# REST API's

Alle nieuwe DSO-gebaseerde API's zijn te vinden onder het
[https://api.data.amsterdam.nl/v1/](https://api.data.amsterdam.nl/api/swagger/?url=/v1/)
endpoint. De individuele datasets worden toegelicht op
de [datasets](/v1/docs/index.html#overzicht-datasets) pagina.

<aside class="tip">
<h4 class="title">Tip</h4>

Een overzicht van alle DataPunt API's is te vinden
op: <a href="/">https://api.data.amsterdam.nl/</a>.
</aside>

## Beschikbare endpoints

De datasets ondersteunen de volgende HTTP operaties:

| Verzoek                           | Resultaat                              |
| --------------------------------- | -------------------------------------- |
| `GET /v1/{dataset}/{tabel}/`      | De lijst van alle records in een tabel |
| `GET /v1/{dataset}/{tabel}/{id}/` | Een individueel record uit de tabel    |

Bijvoorbeeld:

``` bash
curl https://api.data.amsterdam.nl/v1/gebieden/buurten/
curl https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000092.1/
```

Wanneer een pagina direct met de browser opgevraagd wordt dan worden de
resultaten als een doorklikbare HTML pagina getoond. Bijvoorbeeld:
<https://api.data.amsterdam.nl/v1/gebieden/buurten/>. Door de header
`Accept: application/hal+json` te sturen wordt altijd een JSON response
geforceerd. Dit kan ook met de query parameter `?_format=json`

## Gebruik API Keys

Je kunt een sleutel verkrijgen via het [online formulier](https://keys.api.data.amsterdam.nl/clients/v1/register/).
Geef deze sleutel bij iedere http-aanvraag met de `X-Api-Key` header mee, bijvoorbeeld:

    curl https://api.data.amsterdam.nl/v1/gebieden/wijken/ -H "X-Api-Key: very...long...token".

Voor WFS/geo-tools die geen request headers ondersteunen is ook mogelijk om
de queryparameter `?x-api-key=...` te gebruiken.

Door de API key kunnen we contact houden met de gebruikers van onze API's.
Zo kunnen we gebruikers informeren over updates, en inzicht krijgen in het gebruik van de API's.
Voor data-eigenaren is dit waardevolle informatie.

<aside class="note">
  <h4 class="title">Note</h4>

  NB: De API-sleutel wordt alleen gebruikt om het gebruik van onze API's te registreren.
  Deze sleutel biedt geen <a href="authorization.html">authenticatie of autorisaties</a> voor de API's.
</aside>

## Functionaliteit

De API's ondersteunen mogelijkheden tot:

* [Paginering](pagination.md)
* [Filtering](filtering.md)
* [Minder velden ontvangen](fields.md)
* [Sorteren van resultaten](sort.md)
* [Relaties direct insluiten](embeds.md)
* [Exportformaat opgeven](formats.md)
* [Geometrie projecties](projections.md)
* [Autorisatie](authorization.md)
* [Temporele Datasets](temporal.md)
* [Subresources](subresources.md)

## De DSO Standaard

De API's op het `/v1/` endpoint volgen de landelijke [DSO
standaard](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/)
om een eenduidige wijze te bieden voor afnemers.

Hierdoor kom je als technisch gebruiker o.a. de volgende elementen
tegen:

* HAL-JSON links, zoals: `{"_links": {"self": {"href": ..., "title":
    ...}}}`
* Met [?_expandScope={veld1},{veld2}](embeds.md) worden relaties
    getoond in de `_embedded` sectie.
* Met [?_expand=true](embeds.md) worden alle relaties uitgevouwen
    in de `_embedded` sectie.
* Met [?_fields=...](fields.md) kunnen een beperkte set van velden
    opgevraagd worden.
* [Sortering](sort.md) met `?_sort={veldnaam},-{desc veldnaam}`
* [Filtering](filtering.md) op velden via de query-string.
* [Tijdreizen](temporal.md) met de `?geldigOp=...` parameter.
* [Paginering](pagination.md) en `X-Pagination-*` headers.
* [Geometrie projecties](projections.md) via de `Accept-Crs` header.
* Responses geven het object terug, zonder envelope.
