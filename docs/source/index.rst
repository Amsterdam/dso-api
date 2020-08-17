Amsterdam DataPunt API Documentatie
===================================

In deze pagina's geven we uitleg hoe de API diensten van Datapunt afgenomen worden.

.. note::
   Naast de API's van DataPunt worden door andere partijen nog diverse API's aangeboden.
   Deze vind je in de `datasetcatalogus <https://data.amsterdam.nl/datasets/zoek/?filters=distributionType%3Bapi>`_.
   Deze documentatie richt zich tot de API's van DataPunt, onderdeel van OIS (Onderzoek, Informatie en Statistiek)
   van de Gemeente Amsterdam.

Om zoveel mogelijk afnemers te kunnen bedienen, ondersteunen we diverse koppelingen.
Zo zal een mobiele-app ontwikkelaar eerder een :doc:`REST-API <generic/rest>` gebruiken,
en een GIS-professional de :doc:`WFS-koppeling <generic/wfs>` gebruikt.
Tot slot worden er ook volledige CSV en GeoJSON exports ondersteund.

.. toctree::
   :caption: Algemene uitleg:
   :maxdepth: 2

   generic/rest.rst
   generic/wfs.rst
   generic/temporele_datasets.rst

.. toctree::
   :caption: Datasets:
   :maxdepth: 3

   datasets/index
   wfs-datasets/index
