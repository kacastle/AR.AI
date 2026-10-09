from dataclasses import replace
from datetime import date, timedelta

import pytest

from backend.engine import scoring
from backend.engine.state import new_state

TODAY = date(2026, 10, 9)


def run(rules, state, outcomes):
    """outcomes: list of (support-independent) first-try results; result value from the state's support."""
    for ok in outcomes:
        result = scoring.item_result(rules, state.support_level, 1 if ok else 3, correct=True)
        state = scoring.apply_item(rules, state, result, ok, TODAY)
    return state


def test_new_score_formula(rules):
    assert scoring.new_score(rules, 0.0, 1.0) == pytest.approx(0.3)
    assert scoring.new_score(rules, 0.5, 0.0) == pytest.approx(0.35)


@pytest.mark.parametrize("support,attempt,correct,expected", [
    ("alone", 1, True, 1.0),
    ("guide", 1, True, 0.7),
    ("alone", 2, True, 0.7),
    ("show", 1, True, 0.4),
    ("alone", 5, True, 0.4),   # rebuilt after the answer was shown
    ("alone", 1, False, 0.0),
])
def test_item_result(rules, support, attempt, correct, expected):
    assert scoring.item_result(rules, support, attempt, correct) == expected


def test_support_moves_up_after_3_correct(rules):
    s = new_state("sk_vowels", rules)
    assert s.support_level == "show"
    s = run(rules, s, [True, True])
    assert s.support_level == "show"
    s = run(rules, s, [True])
    assert s.support_level == "guide"
    s = run(rules, s, [True, True, True])
    assert s.support_level == "alone"
    s = run(rules, s, [True, True, True])
    assert s.support_level == "alone"   # top level


def test_support_moves_down_after_2_wrong(rules):
    # High score so the two wrong items do not drop the skill into reteach (which resets support to show).
    s = replace(new_state("sk_vowels", rules), support_level="alone", score=0.95)
    s = run(rules, s, [False])
    assert s.support_level == "alone"
    s = run(rules, s, [False])
    assert s.support_level == "guide"


def test_support_never_below_show(rules):
    s = run(rules, new_state("sk_vowels", rules), [False] * 4)
    assert s.support_level == "show"


def test_falling_into_reteach_resets_support_to_show(rules):
    s = replace(new_state("sk_vowels", rules), support_level="guide", score=0.65)
    s = scoring.apply_item(rules, s, 0.0, False, TODAY)
    assert s.score < rules.thresholds.reteach_below
    assert scoring.band(rules, s) == "reteach"
    assert s.support_level == "show"


def test_mastery_needs_score_attempts_and_last_3_correct(rules):
    s = replace(new_state("sk_vowels", rules), support_level="alone", score=0.9, attempts=6)
    s = run(rules, s, [True])
    assert not s.mastered          # 7 attempts, below min_attempts 8
    s = run(rules, s, [True])
    assert not s.mastered          # 8 attempts but only 2 correct in a row
    s = run(rules, s, [True])
    assert s.mastered
    assert s.mastered_at == TODAY
    assert s.review_step == 0
    assert s.next_review_at == TODAY + timedelta(days=rules.review.days[0])
    assert scoring.band(rules, s) == "mastered"


def test_new_learner_who_is_always_right_masters_the_skill(rules):
    s = run(rules, new_state("sk_vowels", rules), [True] * 12)
    assert s.mastered
    assert s.support_level == "alone"
