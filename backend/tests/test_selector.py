import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from backend.engine import review, selector
from backend.engine.state import new_state

TODAY = date(2026, 10, 9)


def rng():
    return random.Random(0)


def mastered(rules, skill_id):
    return replace(new_state(skill_id, rules), score=0.9, support_level="alone", mastered_at=TODAY,
                   review_step=0, next_review_at=TODAY + timedelta(days=1))


def test_new_learner_starts_at_first_skill_with_full_support(content):
    p = selector.pick_next(content, {}, TODAY, [], [], rng=rng())
    assert p.skill_id == "sk_vowels"
    assert p.task_type == "missing_letter"
    assert p.support_level == "show"
    assert p.prefill == p.answer
    assert not p.is_review and not p.is_easy


def test_weakest_unlocked_skill(content, rules):
    states = {"sk_vowels": mastered(rules, "sk_vowels"),
              "sk_letters_1": replace(new_state("sk_letters_1", rules), score=0.3)}
    assert selector.weakest_unlocked_skill(content, states).id == "sk_letters_1"
    # sk_cv_1 (score 0) is locked until sk_letters_1 is mastered.
    states["sk_letters_1"] = mastered(rules, "sk_letters_1")
    assert selector.weakest_unlocked_skill(content, states).id == "sk_cv_1"


def test_comprehension_and_empty_skills_are_not_chosen_for_tile_turns(content):
    ids = {s.id for s in selector.tile_skills(content)}
    assert "sk_comp_literal" not in ids      # practiced in the story turn
    assert "sk_letters_2" not in ids         # has no items in content.json
    assert "sk_sentence_1" in ids            # sentence_builder items


def test_due_review_skill_comes_first(content, rules):
    states = {"sk_vowels": mastered(rules, "sk_vowels")}
    skill, is_review = selector.choose_skill(content, states, TODAY)
    assert (skill.id, is_review) == ("sk_letters_1", False)   # review not due yet
    skill, is_review = selector.choose_skill(content, states, TODAY + timedelta(days=1))
    assert (skill.id, is_review) == ("sk_vowels", True)
    assert review.is_due(states["sk_vowels"], TODAY + timedelta(days=1))


@pytest.mark.parametrize("results,level", [
    ([True] * 10, "hard"),
    ([True] * 9 + [False], "normal"),    # 0.9 is not above 0.9
    ([True] * 5 + [False] * 5, "easy"),
    ([True] * 6 + [False] * 4, "normal"),
    ([False] * 9, "normal"),             # fewer than 10 answers
])
def test_difficulty_window(rules, results, level):
    assert selector.difficulty(results, rules) == level


def test_ng_words_always_get_n_and_g(content, rules):
    for word in [w for w in content.data.words if "ng" in w.tiles]:
        for count in rules.difficulty.distractor_tiles.values():
            d = selector.letter_distractors(word, rules, count)
            assert "n" in d and "g" in d, word.id
    # even when content.json does not list them
    word = content.words_by_id["w_ngipin"].model_copy(update={"distractor_tiles": ["e", "a"]})
    assert {"n", "g"} <= set(selector.letter_distractors(word, rules, 2))


def test_distractor_count_follows_difficulty(content, rules):
    word = content.words_by_id["w_bahay"]
    for level, n in rules.difficulty.distractor_tiles.items():
        assert len(selector.letter_distractors(word, rules, n)) == n, level


def test_tiles_contain_the_answer_plus_distractors(content, rules):
    skill = content.skills_by_id["sk_ng"]
    word = content.words_by_id["w_ngipin"]
    state = replace(new_state("sk_ng", rules), attempts=0)
    p = selector.build_pick(content, skill, state, word, "normal", False, False, rng())
    assert p.task_type == "dictation_letters"
    assert sorted(p.tiles) == sorted(word.tiles + selector.letter_distractors(word, rules, 3))
    assert p.tiles.count("n") >= 2 and "g" in p.tiles


@pytest.mark.parametrize("support,prefill", [
    ("show", ["b", "a", "h", "a", "y"]),
    ("guide", ["b", "", "", "", ""]),
    ("alone", ["", "", "", "", ""]),
])
def test_prefill_by_support_level(content, rules, support, prefill):
    skill = content.skills_by_id["sk_cvc_final"]
    state = replace(new_state(skill.id, rules), support_level=support)
    p = selector.build_pick(content, skill, state, content.words_by_id["w_bahay"], "normal", False, False, rng())
    assert p.task_type == "dictation_letters"
    assert p.prefill == prefill


def test_missing_letter_leaves_the_skill_letter_empty(content, rules):
    skill = content.skills_by_id["sk_vowels"]
    state = replace(new_state(skill.id, rules), support_level="alone")
    p = selector.build_pick(content, skill, state, content.words_by_id["w_aso"], "normal", False, False, rng())
    assert p.task_type == "missing_letter"
    assert p.prefill == ["", "s", "o"]
    assert p.answer == ["a", "s", "o"]
    assert "a" in p.tiles and len(p.tiles) == 1 + 3


def test_task_type_rotates_with_attempts(content, rules):
    skill = content.skills_by_id["sk_vowels"]
    word = content.words_by_id["w_aso"]
    types = [selector.choose_task_type(content, skill, replace(new_state(skill.id, rules), attempts=a), word)
             for a in range(3)]
    assert types == ["missing_letter", "dictation_letters", "missing_letter"]


def test_used_items_are_avoided_and_easy_means_short(content):
    skill = content.skills_by_id["sk_vowels"]
    items = selector.skill_items(content, skill)
    first = selector.choose_item(items, [], "normal")
    assert selector.choose_item(items, [first.id], "normal").id != first.id
    easy = selector.choose_item(items, [], "easy")
    assert len(easy.syllables) == min(len(i.syllables) for i in items)


def test_when_all_items_are_used_the_oldest_comes_back(content):
    items = selector.skill_items(content, content.skills_by_id["sk_vowels"])
    used = [i.id for i in items[3:]] + [i.id for i in items[:3]]   # items[3] was seen longest ago
    assert selector.choose_item(items, used, "normal").id == items[3].id


def test_easy_item_comes_from_a_mastered_skill(content, rules):
    states = {"sk_vowels": mastered(rules, "sk_vowels"),
              "sk_letters_1": replace(new_state("sk_letters_1", rules), score=0.2)}
    p = selector.pick_next(content, states, TODAY, [], [False] * 3, easy=True, rng=rng())
    assert p.is_easy and p.skill_id == "sk_vowels"
