# Relaties direct insluiten

Bij iedere relatie wordt er een hyperlink meegegeven om het object op te
vragen. Echter kunnen alle objecten ook in een enkele request opgehaald
worden. Dit is zowel voor de client als server efficiënter.

Gebruik hiervoor één van volgende opties:

  - Door `?_expand=true` worden alle relaties uitgevouwen in de
    `_embedded` sectie.
  - Door `?_expandScope={veld1},{veld2}` worden specifieke relaties
    getoond in de `_embedded` sectie.

De volgende aanroepen zijn identiek:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/buurten/?_expand=true'

curl 'https://api.data.amsterdam.nl/v1/gebieden/buurten/?_expandScope=ligtInWijk'
```

De response bevat zowel het "buurt" object als de "wijk":

``` javascript
{
    "_links": {
        // ...
    },
    "_embedded": {
        "buurten": [
            {
                "_links": {
                    "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#buurten",
                    "self": {
                        "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000078/?volgnummer=1",
                        "title": "03630000000078.1",
                        "volgnummer": 1,
                        "identificatie": "03630000000078"
                    },
                    "buurtenWoningbouwplan": [],
                    "buurtenStrategischeruimtes": [],
                    "ligtInWijk": {
                        "href": "https://api.data.amsterdam.nl/v1/gebieden/wijken/03630012052036/?volgnummer=1",
                        "title": "03630012052036.1",
                        "volgnummer": 1,
                        "identificatie": "03630012052036"
                    }
                },
                "code": "A00a",
                "naam": "Kop Zeedijk",
                "cbsCode": "BU03630000",
                "geometrie": {
                    "type": "Polygon",
                    "coordinates": [
                        // ...
                    ]
                },
                "ligtInWijkVolgnummer": 1,
                "ligtInWijkIdentificatie": "03630012052036",
                "ligtInWijkId": "03630012052036",
                "documentdatum": null,
                "documentnummer": null,
                "eindGeldigheid": null,
                "beginGeldigheid": "2006-06-12",
                "registratiedatum": "2018-10-25T12:17:48",
                "id": "03630000000078.1"
            }
        ],
        "ligtInWijk": [
            {
                "_links": {
                    "schema": "https://schemas.data.amsterdam.nl/datasets/gebieden/gebieden#wijken",
                    "self": {
                        "href": "https://api.data.amsterdam.nl/v1/gebieden/wijken/03630012052036/?volgnummer=1",
                        "title": "03630012052036.1",
                        "volgnummer": 1,
                        "identificatie": "03630012052036"
                    },
                    "ligtInStadsdeel": {
                        "href": "https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/03630000000018/?volgnummer=3",
                        "title": "03630000000018.3",
                        "volgnummer": 3,
                        "identificatie": "03630000000018"
                    }
                },
                "code": "A00",
                "naam": "Burgwallen-Oude Zijde",
                "cbsCode": "WK036300",
                "geometrie": {
                    "type": "Polygon",
                    "coordinates": [
                        // ...
                    ]
                },
                "documentdatum": null,
                "documentnummer": null,
                "eindGeldigheid": null,
                "beginGeldigheid": "2006-06-12",
                "ligtInStadsdeelVolgnummer": 3,
                "ligtInStadsdeelIdentificatie": "03630000000018",
                "registratiedatum": "2018-10-25T12:17:33",
                "id": "03630012052036.1"
            }
        ]
    },
    "page": {"number": 1, "size": 1, "totalElements": 973, "totalPages": 973}
}
```
