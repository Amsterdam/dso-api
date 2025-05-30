# Minder velden ontvangen

Met de `?_fields=` parameter wordt de grootte van de resultaten
ingeperkt tot enkel de relevante velden die de client nodig heeft. Dit
geeft betere performance, voor zowel de client als server. Er zijn een
aantal notatievormen mogelijk:

| Parameter                           | Werking                                                       |
| ----------------------------------- | ------------------------------------------------------------- |
| `?_fields={veld1},{veld2}`          | Alleen opgegeven velden worden teruggegeven.                  |
| `?_fields=-{veld1},-{veld2}`        | De uitgesloten velden worden NIET teruggegeven.               |
| `?_fields={veld1},{veld2.subveld}`  | Alleen opgegeven velden van relaties worden terugegeven.      |
| `?_fields={veld1},-{veld2.subveld}` | Alleen `veld1`, maar alles van `veld2` behalve het `subveld`. |

Wanneer je alleen specifieke velden opgeeft, wordt de rest weggelaten:

``` bash
curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?_fields=geometry,soortPaaltje'
```

Met het min-teken wordt aangegeven dat alle velden worden teruggegeven,
met uitzondering van het opgegeven veld:

``` bash
curl 'https://api.data.amsterdam.nl/v1/fietspaaltjes/fietspaaltjes/?_fields=-area,-noodzaak'
```

<aside class="note">
<h4 class="title">Note</h4>

In plaats van `_fields` wordt ook `fields` ondersteund, maar `_fields`
heeft de voorkeur.
</aside>

<aside class="note">
<h4 class="title">Note</h4>

Het is niet mogelijk om velden tegelijk in te sluiten en uit te sluiten
op hetzelfde object/niveau.
</aside>

Wanneer er relaties worden teruggegeven (zowel geneste structuren, als
ingesloten relaties met `?_expandScope`), werkt de `?_fields=` logica
hiervoor ook:

``` bash
curl 'https://api.data.amsterdam.nl/v1/bag/woonplaatsen/?_expandScope=heeftDossier.heeftBrondocumenten&_fields=naam,heeftDossier,heeftDossier.heeftBrondocumenten.documentnummer'
```

Per niveau kunnen velden worden ingesloten en uitgesloten. Het opgeven
van een geneste uitsluiting betekend dat het hoofdobject zelf wel
ingesloten wordt.
