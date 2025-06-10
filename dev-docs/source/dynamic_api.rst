Dynamic API Endpoints
=====================

The project follows the standard Django REST Framework "router" logic
together with viewsets.

There is one twist.
Since all :doc:`models are dynamically constructed <dynamic_models>`,
the view classes, serializer classes and URL's are also dynamically constructed at startup.

.. admonition:: Instances vs classes

    Views and serializer objects (i.e., their *instances*) are always instantiated during a request.
    What we do differently is that the view and serializer *classes* are also dynamically constructed.

Serializer Construction
-----------------------

In this project, no handwritten serializer definitions can be found.
Instead, the serializer class is dynamically constructed.
To demonstrate the basic principle:

.. code-block:: python

    factory = DjangoModelFactory(dataset)
    MyModel: type[DynamicModel] = factory.build_model(table_schema)

    MySerializerClass: type[DynamicSerializer] = serializer_factory(MyModel)

    @api_view()
    def view(request):
        queryset = MyModel.objects.all()
        serializer = MySerializerClass(data=queryset)
        return Response(serializer.data)

The :func:`~dso_api.dynamic_api.serializers.serializer_factory` function
constructs all fields according to the model layout and schema definition.

.. tip::

    To view what a handwritten serializer would look like,
    call ``manage.py dump_serializers [appname]`` from the command line.
    The ``--format=nested`` options gives a pseudo-python layout to understand nested relations better.

Viewset Construction
--------------------

The viewsets are also dynamically constructed.
This basically works like this:

.. code-block:: python

    MyViewSetClass: type[DynamicApiViewSet] = viewset_factory(MyModel)

    router = DefaultRouter()
    router.register('urlpath/', MyViewSetClass)

    urlpatterns = router.urls

By dynamically constructing the viewset classes (instead of using custom properties)
the view logic integrates nicely with tools like Django's ``reverse()``,
DRF's ``HyperlinkedRelatedField`` and the OpenAPI generator.
Those all assume there are hard-coded view classes and URLs in the project.

The :func:`~dso_api.dynamic_api.views.api.viewset_factory` function calls various other factories,
including the :func:`~dso_api.dynamic_api.serializers.serializer_factory` function mentioned above.

Full Initialization
-------------------

To construct the API, the REST Framework ``DefaultRouter`` class is extended
as :class:`~dso_api.dynamic_api.routers.DynamicRouter`. It is the startpoint for
all dynamic class construction, including the model, viewsets and serializer classes.

.. graphviz::

    digraph foo {

      rankdir = LR;

      DynamicRouter [shape=box]

      get_models [label="DataSet.objects.filter(...)" shape=none]
      create_models [label="dataset.create_models()" shape=none]
      build_models [label="DjangoModelFactory.build_models()" shape=none]
      viewset_factory [label="viewset_factory()" shape=none]
      serializer_factory [label="serializer_factory()" shape=none]
      filterset_factory [label="filterset_factory()" shape=none]

      DynamicRouter -> get_models
      DynamicRouter -> create_models
      create_models -> build_models

      DynamicRouter -> viewset_factory
      viewset_factory -> serializer_factory
      viewset_factory -> filterset_factory

    }

Each construction of these classes follow the same pattern:
there is a factory method and base class that implements most logic in plain Python.
Those base classes can be found in the :mod:`dso_api.dynamic_api` package:

* :class:`~dso_api.dynamic_api.serializers.DynamicSerializer`
* :class:`~dso_api.dynamic_api.filtersets.DynamicFilterSet`
* :class:`~dso_api.dynamic_api.views.api.DynamicApiViewSet`

The factory methods create a new class, which inherits those base classes
and fill in the attributes for the "dataset", "model" and fields.

When all viewset classes are constructed, reading ``router.urls`` returns all available endpoints
as if it was hard-coded. The ``urls.py`` logic of :mod:`dso_api.dynamic_api.urls` module
exposes those endpoints to Django.
