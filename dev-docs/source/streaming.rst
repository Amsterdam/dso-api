Streaming Output
================

Since the DSO-API offers huge datasets (e.g. all buildings in Amsterdam),
the output is written using a streaming response.
This greatly improves the performance and reduces memory consumption.

Standard REST Framework
-----------------------

A standard REST framework project follows these steps:

.. graphviz::

   digraph foo {
        rankdir=LR
        node [shape=cds]
        edge [style=invis minlen=1]

        paginate [label="paginate (queryset)"]
        paginate2 [label="wrap in page"]
        render [label="render to JSON"]
        write [label="write response"]

        collect -> filter -> paginate -> serialize -> paginate2 -> render -> write
   }

The serializer reads all data in memory, and generates the total JSON dictionary.
Then the paginator can wrap it, and the rendering cals ``json.dumps()`` to
convert this complete structure to a JSON message.
Finally, the total output is written to the client.

For huge datasets, this is problematic. It uses a lot of memory.
The whole complete table data is read in memory, the ``QuerySet`` caches all results,
and the whole JSON string is stored in memory before writing any output.
For a single request, this can create a peak of 1GB in memory usage to handle that amount of data.

Streaming Design
----------------

Ideally, individual records are written to the client while the table is being read.
Then, the memory usage would stay low because a records are processed one by one in the pipeline.

Python offers a generator pattern to read data while it's being retrieved.
Django also has ``QuerySet.iterator()`` to process data one record at a time
and a ``StreamingHttpResponse`` class that allows the WSGI server to read
the response body from a generator/iterator.

Unfortunately, each step inside the Django REST Framework pipeline breaks the streaming behavior.
Whenever code reads all all incoming data upfront, the whole chain of streaming records breaks.
Hence, all steps were altered to work with generators:

.. graphviz::

   digraph foo {
        rankdir=LR
        node [shape=cds height=0.7]
        edge [style=invis minlen=1]

        collect [label="QuerySet.iterator()"]
        collect2 [label="ChunkedQuerySetIterator"]
        paginate [label="paginate without list()"]
        serialize [label="serializer.data\nReturnGenerator"]
        paginate2 [label="wrap in page"]
        render [label="render single objects"]
        footer [label="write footer"]
        response [label="start StreamingResponse"]

        collect -> paginate -> serialize -> paginate2 -> response -> render -> footer
        collect2 -> paginate
        {rank=same; collect; collect2}
        collect -> collect2 [xlabel="or"]
   }

The following steps are taken:

* Serializers read using ``QuerySet.iterator()`` whenever possible.
* Serializers return a ``ReturnGenerator`` instead of a ``ReturnList``.
* The paginator delegates most rendering to the output format; it only adds the basic structure.
* The next/previous links are determined *after* rendering all main objects.
* Our custom ``HALJSONRenderer`` and ``GeoJSONRenderer`` classes support generators.
* The rendering classes perform ``json.dumps()`` calls on single records.
* The ``Response`` class is replaced by a ``StreamingResponse`` class.

Chunked JSON Rendering
----------------------

The JSON response is written by selectively applying ``json.dumps()``.
The idea is to write some object layout manually, and leverage ``json.dumps()`` where possible.
It basically looks like:

.. code-block:: python

    yield '{["_embedded": ['

    # write main listing:
    for record in generator:
        if not first:
            yield ",\n"
        yield json.dumps(record)

    yield "],\n"

    # write "_links" and "page" parts without the opening/closing braces:
    yield json.dumps(footer_links)[1:-1]
    yield "}\n"


Additional Optimizations
------------------------

Output Buffering
~~~~~~~~~~~~~~~~

To avoid too many back/forth calls from the response-generator
and the WSGI server, the produced output is submitted in chunks of 4096kB.
Otherwrite an OS ``write()`` call might happen for a simple ``yield "}"`` statement.

Next Link Optimization
~~~~~~~~~~~~~~~~~~~~~~

A standard paginator would do an expensive ``COUNT(*)`` on the table
and use that to tell whether there are additional pages.
We've optimized this by requesting one extra record from the database at the end of a page.
This sentinel record is not rendered. Its existence indicates that there is another page available.

This does mean the next/previous links have to be written at end of the response,
after all main objects have been seen. This is handled by writing the main JSON object in chunks.

Fields like a "total page count" and "total results" are no longer available, but rarely needed either.
Typically clients only need a link to the next page.
The ``?_count=true`` query parameter can be provided when a client does need a result count.

Error Handling
~~~~~~~~~~~~~~

When an error occurs during streaming, it's not possible to send out a HTTP 500 "Internal Server" error.
After all, the header (with HTTP 200 OK) is already submitted,
and possibly even more content of the first few records.
All the WSGI server can do is stop writing and close the connection.
This gives a confusing situation, with either an unparsable JSON document,
or a incomplete CSV export that might look finished. This is solved in two ways.

First the ``peek_iterable()`` function takes a look at the first
record in the generator. This triggers the database query execution,
and any on-demand parsing (needed for the ``Content-Crs`` header).
At this point, any raised exceptions still trigger a HTTP 500 error.

Only then the streaming response starts.

This is mediated by wrapping the response generator inside a ``try..except`` block.
When an error happens during the streaming phase, a proper message
like ``/* aborted by exception ... */`` can be written to the client.

Embedding Solution
~~~~~~~~~~~~~~~~~~

While records are streamed one at a time, the embedding still needs to track all records
to find out what related records should be fetched. Fortunately, the results only have
to be written to the client after the first section of ``_embedded`` is written.

To solve this, an ``ObservableIterator`` wraps the ``QuerySet.iterator()`` and monitors which
objects are written to the client. Meanwhile, it tracks all related object ID's in a list.
Once the main objects are written to the client, all related identifiers are known
and can be queried at once.

For nested embedding, this isn't possible. Those objects have to be included in a nested
``_embedded`` section within the current section that is written to the client.
Hence those relations are queried directly, with some prefetching optimizations
on the embedded section to avoid many repeated queries.

Prefetching Optimization
~~~~~~~~~~~~~~~~~~~~~~~~

Before Django 4.1, using ``QuerySet.iterator()`` was incompatible with ``QuerySet.prefetch_related()``.
This was fixed by letting Django fetch the results in chunks and perform ``prefetch_related()`` on each chunk to retrieve related objects.

However, this optimization is avoided here as our ``ChunkedQuerySetIterator`` has more optimizations.
It also tracks the most recently retrieved prefetches so the next batch likely doesn't need an extra prefetch.
