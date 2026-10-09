from dataclasses import replace
from datetime import date, timedelta

from backend.engine import review
from backend.engine.state import new_state

TODAY = date(2026, 10, 9)
ALL = ["sk_vowels", "sk_letters_1", "sk_cv_1", "sk_cvcv_1", "sk_ng", "sk_cvc_final", "sk_sentence_1",
       "sk_comp_literal"]


def mastered(rules):
    return review.start_review(new_state("sk_vowels", rules), rules, TODAY)


def test_review_steps_follow_rules_days(rules):
    assert rules.review.days == [1, 3, 7, 14]
    s = mastered(rules)
    assert s.next_review_at == TODAY + timedelta(days=1)
    day = TODAY
    for days in [3, 7, 14]:
        day = s.next_review_at
        assert review.is_due(s, day)
        s = review.apply_review(s, True, rules, day)
        assert s.next_review_at == day + timedelta(days=days)
    s = review.apply_review(s, True, rules, s.next_review_at)
    assert s.next_review_at is None and s.mastered   # all steps done


def test_not_due_before_date(rules):
    s = mastered(rules)
    assert not review.is_due(s, TODAY)
    assert review.is_due(s, TODAY + timedelta(days=1))


def test_failed_review_resets_to_practice(rules):
    s = replace(mastered(rules), score=0.95, support_level="alone")
    s = review.apply_review(s, False, rules, TODAY + timedelta(days=1))
    assert s.score == rules.review.fail_score == 0.7
    assert not s.mastered
    assert s.review_step is None and s.next_review_at is None
    assert s.support_level == rules.support.start["practice"]


# ---------- placement ----------

def answers(passed, failed):
    out = {s: [True, True] for s in passed}
    out.update({s: [True, False] for s in failed})
    return out


def test_placement_all_passed_is_high_emergent(rules):
    r = review.placement_status(answers(ALL, []), rules)
    assert r.done and r.passed == ALL and r.start_skill is None
    assert r.profile == "high_emergent"


def test_placement_stops_after_2_failed_skills_in_a_row(rules):
    a = answers([], ["sk_vowels", "sk_letters_1"])
    r = review.placement_status(a, rules)
    assert r.done
    assert r.failed == ["sk_vowels", "sk_letters_1"]
    assert r.start_skill == "sk_vowels"
    assert r.profile == "low_emergent"
    assert review.next_placement_skill(a, rules) is None


def test_placement_one_of_two_correct_fails_the_skill(rules):
    r = review.placement_status(answers(ALL[1:], ["sk_vowels"]), rules)
    assert "sk_vowels" in r.failed


def test_placement_fail_before_cvcv_is_low_emergent(rules):
    passed = [s for s in ALL if s != "sk_cv_1"]
    r = review.placement_status(answers(passed, ["sk_cv_1"]), rules)
    assert r.done and r.profile == "low_emergent" and r.start_skill == "sk_cv_1"


def test_placement_fail_at_cvcv_or_later_is_high_emergent(rules):
    passed = ["sk_vowels", "sk_letters_1", "sk_cv_1", "sk_ng", "sk_sentence_1", "sk_comp_literal"]
    r = review.placement_status(answers(passed, ["sk_cvcv_1", "sk_cvc_final"]), rules)
    assert r.done and r.profile == "high_emergent"
    assert r.start_skill == "sk_cvcv_1"


def test_next_placement_skill_gives_2_items_per_skill_in_order(rules):
    assert review.next_placement_skill({}, rules) == "sk_vowels"
    assert review.next_placement_skill({"sk_vowels": [True]}, rules) == "sk_vowels"
    assert review.next_placement_skill({"sk_vowels": [True, True]}, rules) == "sk_letters_1"


def test_placement_states_start_passed_skills_at_070(rules):
    r = review.placement_status(answers(["sk_vowels", "sk_letters_1"], ["sk_cv_1", "sk_cvcv_1"]), rules)
    states = review.placement_states(r, rules, TODAY)
    assert [s.skill_id for s in states] == ["sk_vowels", "sk_letters_1"]
    assert all(s.score == 0.7 and s.mastered and s.next_review_at is None for s in states)
