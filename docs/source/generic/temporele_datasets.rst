Temporele Datasets
==================

Sommige datasets (BAGH) presenteren historische data en dus bieden eeen "tijd reizen" mogelijkheid aan.


Filtering op versie nummer
--------------------------

Elk object binnen temporele dataset heeft  een of meer versies per ID.

Bijvoorbeeld: `BAGH Riekerpolder Buurt`_ :code:`/v1/bagh/buurt/03630000000477/`

.. code-block::

   {
       ...
       "id": "03630000000477_002",
       "code": "F88a",
       "naam": "Riekerpolder",
       "identificatie": "03630000000477",
       "volgnummer": 2,
       "eindGeldigheid": null,
       "beginGeldigheid": "2010-05-01",
       "registratiedatum": "2018-10-25T05:17:48"
       ...
   }

Dezelfde link met `volgnummer`_ :code:`/v1/bagh/buurt/03630000000477/?volgnummer=1` geeft de eerste versie van `Riekerpolder` buurt.

.. code-block::

   {
       ...
       "id": "03630000000477_002",
       "code": "F88a",
       "naam": "Riekerpolder",
       "identificatie": "03630000000477",
       "volgnummer": 1,
       "eindGeldigheid": "2010-05-01",
       "beginGeldigheid": "2006-06-16",
       "registratiedatum": "2010-04-30T17:00:00"
       ...
   }

   

Filtering op basis van geldigheids datum
----------------------------------------

Objecten binnen een temporele dataset mogen gefilterd worden op basis van geldigheids datum.

Dit kan gedaan worden op basis van :code:`additionalFilters`, gedefinieerd in de Amsterdam Schema definitie van datasets.

BAGH heeft een temporele filter: :code:`geldigOp`. Dit is een filter die zorgt dat:
 - alle objecten waar `geldigOp` valt binnen `beginGeldigheid` en `eindGeldigheids` datums worden getoond,
 - alle links tussen objecten krijgen `geldigOp` referenties


Bijvoorbeeld:

`BAGH Riekerpolder Buurt`_ :code:`/v1/bagh/buurt/03630000000477/`

.. code-block::

   {
       ...
       "id": "03630000000477_002",
       "code": "F88a",
       "naam": "Riekerpolder",
       "identificatie": "03630000000477",
       "volgnummer": 2,
       "eindGeldigheid": null,
       "beginGeldigheid": "2010-05-01",
       "registratiedatum": "2018-10-25T05:17:48"
       ...
   }


Toevoegen van `geldigOp`_ in URI :code:`/v1/bagh/buurt/03630000000477/?geldigOp=2010-04-30` geeft buurt informatie die geldig is op 30 April 2010.


.. code-block::

   {
       ...
       "id": "03630000000477_001",
       "code": "F88a",
       "naam": "Riekerpolder",
       "identificatie": "03630000000477",
       "volgnummer": 1,
       "eindGeldigheid": "2010-05-01",
       "beginGeldigheid": "2006-06-16",
       "registratiedatum": "2010-04-30T17:00:00"
       ...
   }




.. _BAGH Riekerpolder Buurt: /v1/bagh/buurt/03630000000477/
.. _volgnummer: /v1/bagh/buurt/03630000000477/?volgnummer=1
.. _geldigOp: /v1/bagh/buurt/03630000000477/?geldigOp=2010-04-30
