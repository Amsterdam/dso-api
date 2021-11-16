Vector tiles uitlezen (MVT)
===========================

Datasets met een geometrisch veld kunnen uitgelezen worden
in een bestandsindeling die Mapbox Vector Tiles (MVT) heet.
Vergeleken bij WFS laden vector tiles snel en staan ze snel in- en uitzoomen toe.

Een lijst van datasets die vector tiles ondersteunen is beschikbaar op:
https://api.data.amsterdam.nl/v1/mvt/.

In QGIS kunnen vector tiles als volgt worden benaderd:

* In de *Browser* (linker tabblad), rechtermuisklik op *Vector Tiles*,
  dan *Nieuwe algemene verbinding* (*New Generic Connection*).
* De URL is ``https://api.data.amsterdam.nl/v1/mvt/<dataset>/<tabel>/{z}/{x}/{y}.pbf``.
  Vervang ``<dataset>`` en ``<tabel>`` door de namen in kwestie,
  maar laat ``{z}/{x}/{y}`` staan, inclusief de accolades.
* *Min. zoomniveau* (*Min. Zoom Level*) staat standaard op 0. Zet dit op 1.

Van datasets met meer dan één geometrisch veld
wordt momenteel alleen het eerste veld opgeleverd in MVT.
