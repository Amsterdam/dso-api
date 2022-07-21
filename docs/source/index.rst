Amsterdam DataPunt API Documentatie
===================================

In deze pagina's geven we uitleg hoe de API diensten van Datapunt afgenomen worden.

.. note::
   Naast de API's van DataPunt worden door andere partijen nog diverse API's aangeboden.
   Deze vind je in de `datasetcatalogus <https://data.amsterdam.nl/datasets/zoek/?filters=distributionType%3Bapi>`_.
   Deze documentatie richt zich tot de API's van DataPunt, onderdeel van OIS (Onderzoek, Informatie en Statistiek)
   van de Gemeente Amsterdam.

Gemeente Amsterdam biedt haar datasets onder andere aan via een REST API die voldoet aan de
`NL API REST API Design Rules <https://forumstandaardisatie.nl/open-standaarden/rest-api-design-rules>`_.
Daarnaast is ook gekozen de strictere interpretatie van de
`DSO API Strategie 2.0 <https://iplo.nl/digitaal-stelsel/aansluiten/standaarden/api-en-uri-strategie/>`_
te volgen, aangezien het de intentie van de DSO API Strategie is om een interoperabel
koppelvlak voor data-uitwisseling te ontwikkelen dat overeenkomt met de behoeftes
van de Gemeente Amsterdam.

Om zoveel mogelijk afnemers te kunnen bedienen, ondersteunen we diverse koppelingen.
Zo zal een mobiele-appontwikkelaar eerder een :doc:`REST-API <generic/rest>` gebruiken,
en een GIS-professional de :doc:`WFS/MVT-koppelingen <generic/gis>`.
Tot slot worden er ook volledige CSV en GeoJSON exports ondersteund.

.. toctree::
   :caption: Algemene uitleg:
   :maxdepth: 2

   generic/rest.rst
   generic/gis.rst

.. toctree::
   :caption: Naslagwerk datasets:
   :maxdepth: 3

   datasets/index
   wfs-datasets/index
