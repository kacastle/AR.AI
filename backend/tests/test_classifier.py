import pytest

from backend.content import load_content
from backend.engine.classifier import classify

# (expected tiles, given tiles, code). Tiles are lists so that ng stays one tile.
CASES = [
    (["m", "e", "s", "a"], ["m", "i", "s", "a"], "P_SUB_VOWEL"),
    (["b", "a", "t", "a"], ["d", "a", "t", "a"], "P_SUB_CONS"),
    (["b", "a", "h", "a", "y"], ["b", "a", "h", "a"], "P_OMIT_FINAL"),
    (["k", "a", "n", "d", "i", "l", "a"], ["k", "a", "d", "i", "l", "a"], "P_OMIT_MID"),
    (["m", "a", "t", "a"], ["m", "a", "t", "a", "a"], "P_ADD"),
    (["i", "b", "o", "n"], ["i", "b", "n", "o"], "O_ORDER"),
    (["ng", "i", "p", "i", "n"], ["n", "i", "p", "i", "n"], "O_NG"),
    (["ng", "i", "p", "i", "n"], ["n", "g", "i", "p", "i", "n"], "O_NG"),
    (["s", "a", "p", "a", "t", "o", "s"], ["s", "a", "p", "o", "s"], "S_SYLL_MISS"),
]


@pytest.mark.parametrize("expected,given,code", CASES, ids=lambda v: "".join(v) if isinstance(v, list) else v)
def test_required_cases(expected, given, code):
    assert classify(expected, given) == code


def test_correct_answer_has_no_mistake():
    assert classify(["b", "a", "h", "a", "y"], ["b", "a", "h", "a", "y"]) is None


def test_leftmost_mistake_wins():
    # bahay -> pahy: substitution b->p at slot 0 comes before the deleted a.
    assert classify(["b", "a", "h", "a", "y"], ["p", "a", "h", "y"]) == "P_SUB_CONS"
    # mesa -> mis: the vowel substitution comes before the deleted final a.
    assert classify(["m", "e", "s", "a"], ["m", "i", "s"]) == "P_SUB_VOWEL"


def test_every_code_is_in_rules():
    codes = set(load_content().rules.mistake_types)
    assert {code for _, _, code in CASES} <= codes
