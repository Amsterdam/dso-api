"""
Utility methods for use in the django shell.

Example, in the shell:

    $ python ./manage.py shell

    >>> from devtools import get_model
    >>> adressen = get_model("bag","v1","ligplaatsen")

Methods:

get_model: get the (dynamically created) django model for a table
get_viewset: get the (dynamically created) viewset for a table
mvs: get the (dynamically created) model, viewset, serializer for a table as a tuple
"""

from dso_api.dynamic_api.urls import router


def get_model(dataset, table, version):
    try:
        return router.all_models[dataset][version][table]
    except KeyError:
        return None


def get_viewset(dataset, table, version):
    try:
        return next(r[1] for r in router.registry if r[0] == f"/{dataset}/{version}/{table}")
    except StopIteration:
        return None


def mvs(dataset, table, version="v1"):
    """Return model, viewset, and serializer of a table as a tuple.

    Usage:
        lp_model, lp_viewset, lp_serializer = mvs("bag","ligplaatsen")
        lp_model, lp_viewset, lp_serializer = mvs("bag","ligplaatsen", "v1")

    Will return None for things that don't exist.
    """
    model = get_model(dataset, table, version)
    viewset = get_viewset(dataset, table, version)
    serializer = viewset.serializer_class if viewset else None
    return model, viewset, serializer
