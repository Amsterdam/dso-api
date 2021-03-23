Dynamic API Endpoints
=====================

Since all :doc:`models are dynamically constructed <dynamic_models>`,
the views, URL's and serializers are also dynamically constructed at startup.
By using this approach (instead of custom properties) the view logic integrates nicely with
tools like Django's ``reverse()``, DRF's ``HyperlinkedRelatedField`` and the OpenAPI generator.
Their code assumes there are hard-coded views and URLs in the project.

.. graphviz::

    digraph foo {

      rankdir = LR;

      DynamicRouter [shape=box]

      get_models [label="DataSet.objects.filter(...)" shape=none]
      create_models [label="dataset.create_models()" shape=none]
      model_factory [label="model_factory()" shape=none]
      viewset_factory [label="viewset_factory()" shape=none]
      serializer_factory [label="serializer_factory()" shape=none]
      filterset_factory [label="filterset_factory()" shape=none]

      DynamicRouter -> get_models
      DynamicRouter -> create_models
      create_models -> model_factory

      DynamicRouter -> viewset_factory
      viewset_factory -> serializer_factory
      viewset_factory -> filterset_factory

    }

The construction of those objects follows the same pattern as the model construction do:
there is a factory method and base class that implements most logic in plain Python.
Those base classes can be found in the :mod:`dso_api.dynamic_api` package:

* :class:`~dso_api.dynamic_api.serializers.DynamicSerializer`
* :class:`~dso_api.dynamic_api.filtersets.DynamicFilterSet`
* :class:`~dso_api.dynamic_api.views.api.DynamicApiViewSet`

The factory methods create a new class, which inherits those base classes
and fill in the attributes for the "dataset", "model" and fields.

When all viewsets are constructed, reading ``router.urls`` returns all available endpoints
as if it was hard-coded. The ``urls.py`` logic of :mod:`dso_api.dynamic_api.urls` module
exposes those endpoints to Django.
