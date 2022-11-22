# REST API gebruiken

Alle nieuwe DSO-gebaseerde API's zijn te vinden onder het
[https://api.data.amsterdam.nl/v1/](https://api.data.amsterdam.nl/api/swagger/?url=/v1/)
endpoint. De individuele datasets worden toegelicht op de `datasets
</datasets/index>` pagina.

<div class="tip">

<div class="title">

Tip

</div>

Een overzicht van alle DataPunt API's is te vinden op:
<https://api.data.amsterdam.nl/>.

</div>

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
geforceerd. Dit kan ook met de query parameter `_format=json`

**Functionaliteit**

De API's ondersteunen mogelijkheden tot:

<div class="toctree" data-maxdepth="1">

rest/pagination rest/filtering rest/fields rest/sort rest/embeds
rest/formats rest/projections rest/authorization rest/temporal

</div>

## De DSO Standaard

De API's op het `/v1/` endpoint volgen de landelijke [DSO
standaard](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/)
om een eenduidige wijze te bieden voor afnemers.

Hierdoor kom je als technisch gebruiker o.a. de volgende elementen
tegen:

  - HAL-JSON links, zoals: `{"_links": {"self": {"href": ..., "title":
    ...}}}`
  - Met `?_expandScope={veld1},{veld2} <rest/embeds>` worden relaties
    getoond in de `_embedded` sectie.
  - Met `?_expand=true <rest/embeds>` worden alle relaties uitgevouwen
    in de `_embedded` sectie.
  - Met `?_fields=... <rest/fields>` kunnen een beperkte set van velden
    opgevraagd worden.
  - `Sortering <rest/sort>` met `?_sort={veldnaam},-{desc veldnaam}`
  - `Filtering <rest/filtering>` op velden via de query-string.
  - `Tijdreizen <rest/temporal>` met de `?geldigOp=...` parameter.
  - `Paginering <rest/pagination>` en `X-Pagination-*` headers.
  - Responses geven het object terug, zonder envelope.
