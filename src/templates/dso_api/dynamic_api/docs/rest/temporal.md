# Temporele Datasets

Sommige datasets bevatten historische data. Hiermee kan je door vorige
versies van hetzelfde object navigeren. Standaard wordt alleen de
huidige versie teruggegeven voor de API.

Het navigeren naar andere voorkomens/versies noemt de [DSO
standaard](https://aandeslagmetdeomgevingswet.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/)
ook wel "tijdreizen". We spreken hier ook over "temporele" datasets.

## Opbouw identificatie

Elk object binnen een temporele dataset heeft één of meerdere
voorkomens/versies. Ieder object heeft naast de gemeenschappelijke
sleutel bijvoorbeeld een "volgnummer" of "datum". Bij iedere verandering
wordt het vorige record afgesloten, en een nieuw record toegevoegd.

Alle records behouden wel dezelfde primaire identifier (bij ons vaak:
"identificatie"). Een tweede veld wordt gebruikt in een *samengestelde
primaire sleutel* om het object uniek te identificeren (bij ons vaak
"volgnummer").

Andere tabellen kunnen op twee manieren verwijzen naar een temporeel
record. Er kan verwezen worden naar slechts de eerste deel van
identificatie. Ook kan er naar een specifieke versie/voorkomen van het
object verwezen worden.

Naast objecten kunnen ook relaties temporaliteit bevatten. Denk
bijvoorbeeld aan een wijk die gekoppeld wordt aan een nieuw gebied.
Beide objecten blijven dezelfde geldigheid behouden; alleen de relatie
is veranderd.

## Zoekingangen

Er zijn meerdere assen waarop de verschillende "voorkomens" van een
object op te vragen zijn:

| Dimensie (as)  | Omschrijving                    |
| -------------- | ------------------------------- |
| Geldig op      | Wanneer iets actief is.         |
| Beschikbaar op | Invoerdatum van de gegevens.    |
| In werking op  | Regels die eerder/later ingaan. |

Doorgaans is de "geldig op"-dimensie de standaard zoekingang. Dit laat
zien wanneer iets in de echte wereld van toepassing is (materiële
historie).

De "beschikbaar op"-dimensie laat zien wanneer deze verandering ook te
zien is in het systeem (formele historie). Dat kan eerder zijn
(aankondiging van een verandering), maar ook later (bijvoorbeeld
aangifte van geboorte op dag 3). Dit wordt ook gebruikt om beslissingen
te controleren; "toen we destijds keken, zouden we het geldige object
hebben gevonden?".

De "in werking op"-dimensie is vooral bij juridische kwesties van
toepassing. Hierbij kan het gaan om regels die met terugwerkende kracht
gelden. Soms zijn regels al geldig, maar nog niet in werking (zie
bijvoorbeeld de aanloop naar de GDPR/AVG), zijn ze werkzaam met
terugwerkende kracht, of gelden de oude regels nog voor huidige
situaties (bijv. oude systeem van studiefinanciëring bij iedereen
geboren voor 1990).

## Filtering op versienummer

Bijvoorbeeld: de buurt
[Riekerpolder](https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/)
in gebieden/buurten heeft op het moment van schrijven de volgende
attributen:

    {
         "_links": {
             ...
             "self": {
                 "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?volgnummer=2",
                 "title": "03630000000477.2",
                 "volgnummer": 2,
                 "identificatie": "03630000000477"
             },
             ...
         },
         "id": "03630000000477.2"
         "code": "F88a",
         "naam": "Riekerpolder",
         ...
         "beginGeldigheid": "2010-05-01",
         "eindGeldigheid": null,
         "registratiedatum": "2018-10-25T12:17:48",
     }

Dezelfde link met
[?volgnummer=1](https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?volgnummer=1)
geeft de eerste versie van deze buurt:

    {
        "_links": {
            ...
            "self": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?volgnummer=1",
                "title": "03630000000477.1",
                "volgnummer": 1,
                "identificatie": "03630000000477"
            },
            ...
        },
        "id": "03630000000477.1"
        "code": "R88a",
        "naam": "Riekerpolder",
        ...
        "beginGeldigheid": "2006-06-16",
        "eindGeldigheid": "2010-05-01",
        "registratiedatum": "2010-05-01T00:00:00",
    }

## Filtering op basis van geldigheidsdatum

Objecten binnen een temporele dataset mogen gefilterd worden op basis
van geldigheidsdatum. De dataset `gebieden` heeft bijvoorbeeld een
temporeel filter `geldigOp`.

Bijvoorbeeld, opnieuw Riekerpolder, maar nu met
[?geldigOp=2010-04-30](https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?geldigOp=2010-04-30),
geeft versie 1 van die buurt:

    {
        "_links": {
            ...
            "self": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?geldigOp=2010-04-30",
                "title": "03630000000477.1",
                "volgnummer": 1,
                "identificatie": "03630000000477"
            },
            ...
        },
        "id": "03630000000477.1"
        "code": "R88a",
        "naam": "Riekerpolder",
        ...
        "beginGeldigheid": "2006-06-16",
        "eindGeldigheid": "2010-05-01",
        "registratiedatum": "2010-05-01T00:00:00",
    }

De temporele zoekfilters worden ook toegepast in de links/href velden.
