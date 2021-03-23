"""Internal serializer tools to make sure generators are properly handled in DRF."""
import itertools

from rest_framework.utils.serializer_helpers import ReturnList


class ReturnGenerator(ReturnList):
    """A class in the same spirit as DRF's ReturnList / ReturnDict.
    It binds the origin / serializer instance with the returned data.

    To pass the rendering logic, it either needs to inherit from
    GeneratorType, or list.
    """

    def __init__(self, generator, serializer=None):
        super().__init__([], serializer=serializer)
        self.generator = generator

    def __iter__(self):
        """Overwritten to read the generator instead"""
        return iter(self.generator)

    def __repr__(self):
        return f"ReturnGenerator({self.generator})"

    def __bool__(self):
        # Generators are always true, calls to "if data: ..." should not fail.
        return True


def peek_iterable(generator):
    """Take a quick look at the first item of an generator/iterable.
    This returns a modified iterable that contains all elements, inluding the peeked item.
    """
    iterable = iter(generator)  # make sure this is an iterator, so it can't restart.
    try:
        item = next(iterable)
    except StopIteration:
        return None, iterable

    return item, itertools.chain([item], iterable)
