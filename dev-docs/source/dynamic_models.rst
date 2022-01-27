Dynamic Models
==============

The DSO-API uses dynamically generated models, which are constructed from JSON schema definitions.
The central function to construct models is :func:`~schematools.contrib.django.factories.model_factory`.
It builds a Django model based on the imported schema data.

.. graphviz::

    digraph foo {

      ams [label="Amsterdam Schema", shape=note]

      dataset [label="Dataset [model]" shape=box]
      model_factory [label="model_factory()" shape=none]
      custom1 [label="CustomModel1" shape=box]
      custom2 [label="CustomModel2" shape=box]

      ams -> dataset [style=dotted, label="manage.py import_schemas"]
      dataset -> model_factory
      model_factory -> custom1
      model_factory -> custom2

    }

|

.. note::
    The schema files are not imported directly; the ``manage.py import_schemas`` command
    loads the definitions into the :class:`~schematools.contrib.django.models.Dataset`,
    :class:`~schematools.contrib.django.models.DatasetTable` and
    :class:`~schematools.contrib.django.models.DatasetField` models.

Loading Schemas
---------------

To play with the examples, load the schemas first.

The schema files are imported by ``manage.py import_schemas``.
This command reads all available schemas from a schema repository
(:ref:`SCHEMA_URL <SCHEMA_URL>`, default: https://schemas.data.amsterdam.nl/datasets/)
and updates the metadata tables accordingly.

All schema data is saved in the :class:`~schematools.contrib.django.models.Dataset`
model from the :mod:`schematools.contrib.django` package.
Upon startup, DSO-API reads all available dataset schema's from
the :class:`~schematools.contrib.django.models.Dataset` model to construct the models.
When the model construction can't run at startup,
use the :ref:`INITIALIZE_DYNAMIC_VIEWSETS=0 <INITIALIZE_DYNAMIC_VIEWSETS>` variable.

.. tip::

    Run ``manage.py dump_models`` to see the internal model layout that was created.
    This command is also very useful to debug the model factory logic in schematools.

Model Logic
-----------

While the idea of a dynamic model might be daunting, all logic is still implemented in plain Python.
The dynamic models inherit all logic from their base class: :class:`~schematools.contrib.django.models.DynamicModel`.

.. graphviz::

    digraph foo {
      dynamicmodel [label="DynamicModel" shape=box]
      custom1 [label="CustomModel1" shape=box]
      custom2 [label="CustomModel2" shape=box]

      dynamicmodel -> custom1 [dir=back arrowtail=empty]
      dynamicmodel -> custom2 [dir=back arrowtail=empty]
    }

|

Thus, the only "dynamic" part is the translation of the schema to the model field objects.
That's the part after all that would normally be written in Python as well.

.. tip::
    To debug datasets and use their models, you can reuse the router logic
    which already created those models. The following can be used inside ``./manage.py shell``::

        >>> from dso_api.dynamic_api.urls import router
        >>> Model = router.all_models["dataset"]["tablename"]
        >>> Model.objects.all()  # etc..

Internals of model_factory()
----------------------------

Classes can be generated at run-time in Python using the :class:`type` class
or by calling the metaclass. The following code examples are functionally equivalent:

.. code-block:: python

    class Person(models.Model):
        name = models.CharField(max_length=100)

And

.. code-block:: python

    Person = type(
        "Person",
        (models.Model,),
        {
            "name": models.CharField(max_length=100),
        }
    )

This is the logic that :func:`~schematools.contrib.django.factories.model_factory` uses
to create dynamic models. The code looks more extensive, as it reads the schema
definitions to come up with the proper model fields as a dictionary.

.. admonition:: On Metaclasses

    The term metaclass should not to be confused with ``class Meta`` that is
    typically seen in Django code. That construct just holds a bit of metadata.

    A real metaclass constructs a class (``Model = ModelBase(name, bases, attrs)``),
    just like a class constructs an instance (``person = Model(name="John")``).
    Metaclasses are invoked for subclasses too. Django uses this to read the
    hard-coded fields from your model/form/serializer classes.

    When the :class:`type` class is called as ``type(name, bases, attrs)``,
    it uses the metaclass of those base classes to construct the class.
    Hence, it's also possible to call :class:`django.db.models.bases.ModelBase`
    directly instead of :class:`type`, as that's the metaclass of :class:`django.db.models.Model`.

Creating Tables
---------------

When ``manage.py create_tables`` is executed (or ``manage.py import_schemas --create-tables``),
the underlying database tables are created based on the model data.

.. note::

    On production, the tables are typically populated by a job from a separate Airflow instance.
