from django.utils.functional import LazyObject, empty


def unlazy_object(obj):
    if isinstance(obj, LazyObject):
        if obj._wrapped is empty:
            obj._setup()
        return obj._wrapped
    else:
        return obj
