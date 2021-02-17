Temporele Datasets
==================

Sommige datasets bevatten historische data en dus bieden de mogelijkheid van "tijdreizen" aan.
We noemen deze datasets "temporeel". Elk object binnen een temporele dataset heeft een of meer versies, geïdentificeerd door een "volgnummer".


Filtering op versienummer
-------------------------

Bijvoorbeeld: de buurt `Riekerpolder <https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/>`_ in gebieden/buurten heeft op het moment van schrijven de volgende attributen:

.. code-block::

   {
       ...
       "code": "F88a",
       "naam": "Riekerpolder",
       ...
       "volgnummer": 2,
       ...
       "identificatie": "03630000000477",
       ...
       "eindGeldigheid": null,
       "beginGeldigheid": "2010-05-01",
       "registratiedatum": "2010-05-01T00:00:00",
       "id": "03630000000477.2"
   }

Dezelfde link met `volgnummer=1 <https://api.data.amsterdam.nl/v1/gebieden/buurten/03630000000477/?volgnummer=1>`_ geeft de eerste versie van deze buurt:

.. code-block::

   {
       ...
       "code": "F88a",
       "naam": "Riekerpolder",
       ...
       "volgnummer": 1,
       ...
       "identificatie": "03630000000477",
       ...
       "eindGeldigheid": "2010-05-01",
       "beginGeldigheid": "2006-06-16",
       "registratiedatum": "2010-05-01T00:00:00",
       "id": "03630000000477.1"
   }



Filtering op basis van geldigheidsdatum
---------------------------------------

Objecten binnen een temporele dataset mogen gefilterd worden op basis van geldigheidsdatum.
Dit kan gedaan worden met :code:`additionalFilters`, gedefinieerd in de Amsterdam Schema definitie van datasets.

Gebieden heeft een temporeel filter :code:`geldigOp`. Dit is een filter dat ervoor zorgt dat:
 - alle objecten waar `geldigOp` valt tussen de datums `beginGeldigheid` en `eindGeldigheid` worden getoond,
 - alle links tussen objecten referenties `geldigOp` krijgen.


Bijvoorbeeld, opnieuw Riekerpolder, maar nu met `geldigOp=2010-04-30 <https://api.data.amsterdam.nl/v1/gebieden/buurt/03630000000477/?geldigOp=2010-04-30>`_, geeft versie 1 van die buurt:

.. code-block::

   {
       ...
       "code": "F88a",
       "naam": "Riekerpolder",
       ...
       "volgnummer": 1,
       ...
       "identificatie": "03630000000477",
       ...
       "eindGeldigheid": "2010-05-01",
       "beginGeldigheid": "2006-06-16",
       "registratiedatum": "2010-05-01T17:00:00"
       "id": "03630000000477.1",
   }
