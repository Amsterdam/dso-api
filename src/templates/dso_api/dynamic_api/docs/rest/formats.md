# Exportformaat opgeven

De REST API kan de resultaten in andere bestandsformaten presenteren,
zodat deze gegegevens direct in de bijbehorende software ingeladen kan
worden. Standaard wordt de HAL-JSON notatie gebruikt uit de DSO
standaard.

Met het CSV formaat kunnen de gegevens direct in Excel worden ingelezen.

Met de parameter `?_format=` kan dit gewijzigd worden. De volgende
formaten worden ondersteund:

| Parameter          | Toelichting                  | Media type             |
| ------------------ | ---------------------------- | ---------------------- |
| `?_format=json`    | HAL-JSON notatie (standaard) | `application/hal+json` |
| `?_format=geojson` | GeoJSON notatie              | `application/geo+json` |
| `?_format=csv`     | Kommagescheiden bestand      | `text/csv`             |

<div class="note">

<div class="title">

Note

</div>

In plaats van `_format` wordt ook `format` ondersteund, maar `_format`
heeft de voorkeur.

</div>

<div class="warning">

<div class="title">

Warning

</div>

Niet ieder exportformaat ondersteund alle veldtypen die een dataset kan
bevatten. Bij het gebruik van een CSV bestand worden de meer-op-meer
relaties niet opgenomen in de export. In een GeoJSON bestand worden
ingesloten velden opgenomen als losse objecten.

</div>

<div class="tip">

<div class="title">

Tip

</div>

Voor het koppelen van de datasets in GIS-applicaties kun je naast het
GeoJSON formaat ook gebruik maken van de `WFS koppeling <wfs>`.

</div>
