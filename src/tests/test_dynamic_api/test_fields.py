import pytest

from dso_api.dynamic_api.utils import split_on_separator


@pytest.mark.parametrize(
    "instr,result",
    [
        ("aa_bb", ["aa", "bb"]),
        ("aa.bb", ["aa", "bb"]),
        ("aa.bb.cc", ["aa.bb", "cc"]),
        ("aa_bb.cc", ["aa_bb", "cc"]),
        ("aa.bb_cc", ["aa.bb", "cc"]),
    ],
)
def test_split(instr, result):
    assert split_on_separator(instr) == result
