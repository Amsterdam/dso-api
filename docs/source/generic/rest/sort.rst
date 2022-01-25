Sorteren van resultaten
=======================

Gebruik de parameter :samp:`?_sort={veld1},{veld2},{...}` om resultaten te ordenen.
Bijvoorbeeld:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=naam'

Sorteren om meerdere velden is ook mogelijk met :samp:`?_sort={veld1},{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=ingangCyclus,naam'

Gebruik het ``-``-teken om omgekeerd te sorteren :samp:`?_sort=-{veld1},-{veld2}`:

.. code-block:: bash

    curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=-ingangCyclus,naam'

.. note::
    In plaats van ``_sort`` wordt ook ``sorteer`` ondersteund,
    maar ``_sort`` heeft de voorkeur.
