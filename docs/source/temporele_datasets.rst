Temporele Datasets
==================

Somige datasets (BAGH) presenteren historische data en dus bieden "tijd reisen" megelijkheid aan.


Filtering op versie nummer
--------------------------

Elk object binnen temporele dataset heeft  een of meer versies per ID.

Voorbeeld: `BAGH Riekerpolder Buurt`_ :code:`/v1/bagh/buurt/03630000000477/`

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

Hetzelfde link met `volgnummer`_ :code:`/v1/bagh/buurt/03630000000477/?volgnummer=1` geeft eerste versie van `Riekerpolder` buurt.

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

Objecten binnen temporele dataset mogen gefiltered worden op basis van geldigheids datum.

Dit kan gedaan worden op basis van :code:`additionalFilters` gedifineerd in Amsterdam Schema definitie van datasets.

BAGH heeft een temporele filter: :code:`geldigOp`, dit is een filter, die zorgd dat:
 - allen objecten waar `geldigOp` valt binnen `beginGeldigheid` en `eindGeldigheids` datums worden getoond,
 - alle links tussen objecten krijgen `geldigOp` referenties


Voorbeeld:

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


Toevoegen van `geldigOp`_ in URI :code:`/v1/bagh/buurt/03630000000477/?geldigOp=2010-04-30` geeft een buurt informatie die is geldig op 30 April 2010.


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
