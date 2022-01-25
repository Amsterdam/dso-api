Paginering
==========

De REST API geeft de resultaten gepagineerd terug.
De paginagrootte kan aangepast worden door een :samp:`?_pageSize={n}` query parameter toe te voegen aan de request URL.

In de response zijn de volgende elementen te vinden:

.. code-block:: javascript

    {
        "_links": {
            "self": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/"
            },
            "next": {
                "href": "https://api.data.amsterdam.nl/v1/gebieden/buurten/?page=2"
            },
            "previous": {
                "href": null
            }
        },
        "_embedded": {

           // alle objecten...

        },
        "page": {
            "number": 1,
            "size": 20,
            "totalElements": 117,
            "totalPages": 6,
        }
    }

.. note::
    In plaats van ``_pageSize`` wordt ook ``page_size`` ondersteund,
    maar ``_pageSize`` heeft de voorkeur.

Met de velden ``_links.next`` en ``_links.previous`` zijn respectievelijk de volgende en vorige pagina op te vragen.
Meer algemeen kan pagina `n` worden opgevraagd met :samp:`?page={n}`.
Paginanummers beginnen bij één, niet nul.

In het object ``page`` zijn de volgende velden opgenomen:

* ``page.number``: Het huidige paginanummer.
* ``page.size``: De grootte van een pagina.
* ``page.totalElements``: Het aantal objecten in de (gefilterde) resultaat set.
* ``page.totalPages``: Het aantal paginas in de (gefilterde) resultaat set.

`page.totalPages` en `page.totalElements` worden alleen teruggegeven als de `_count` parameter wordt gebruikt.

De velden uit het ``page`` object worden ook als HTTP headers in de response teruggegeven:

* ``X-Pagination-Page``: Het huidige paginanummer.
* ``X-Pagination-Limit``: de grootte van een pagina.
* ``X-Total-Count``: de grootte van een pagina.
* ``X-Pagination-Count``: het aantal paginas voor de gegeven ``_pageSize``.
