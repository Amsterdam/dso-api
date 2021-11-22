from django.utils.functional import LazyObject, empty

DictOfDicts = dict[str, dict[str, dict]]


def unlazy_object(obj):
    if isinstance(obj, LazyObject):
        if obj._wrapped is empty:
            obj._setup()
        return obj._wrapped
    else:
        return obj


def group_dotted_names(dotted_field_names: list[str]) -> DictOfDicts:
    """Convert a list of dotted names to tree."""
    result = {}
    for dotted_name in dotted_field_names:
        tree_level = result
        for path_item in dotted_name.split("."):
            tree_level = tree_level.setdefault(path_item, {})
    return result
