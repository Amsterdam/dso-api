from rest_framework_dso.serializer_helpers import peek_iterable


def test_peek_iterable():
    first, items = peek_iterable([1, 2, 3])
    assert first == 1
    assert list(items) == [1, 2, 3]
    assert list(items) == []  # generator is consumed
