"""Skill score, thresholds and support level changes. All numbers come from rules.json.

One update per item, when the item ends. An item counts as "correct" (for streaks and
"last 3 correct") when the first attempt was right.
"""
from dataclasses import replace
from datetime import date

from backend.engine import review
from backend.engine.state import SkillState


def item_result(rules, support_level: str, attempt: int, correct: bool) -> float:
    """The result value for an item, from rules.score.result_values.

    - never correct                                   -> wrong (0.0)
    - correct only after the answer was shown, or after 2+ hints, or at support "show" -> shown (0.4)
    - correct after 1 hint, or at support "guide"     -> guide_or_1_hint (0.7)
    - correct on the first try at support "alone"     -> alone (1.0)
    """
    v = rules.score.result_values
    if not correct:
        return v["wrong"]
    if attempt > 2 or support_level == "show":
        return v["shown"]
    if attempt == 2 or support_level == "guide":
        return v["guide_or_1_hint"]
    return v["alone"]


def new_score(rules, old: float, result: float) -> float:
    return old + rules.score.alpha * (result - old)


def band(rules, state: SkillState) -> str:
    """reteach / practice / mastered (rules.md section 3)."""
    if state.mastered:
        return "mastered"
    return "reteach" if state.score < rules.thresholds.reteach_below else "practice"


def _move_support(rules, level: str, step: int) -> str:
    levels = rules.support.levels
    i = max(0, min(len(levels) - 1, levels.index(level) + step))
    return levels[i]


def apply_item(rules, state: SkillState, result: float, first_try_correct: bool, today: date) -> SkillState:
    """Update one skill after one item."""
    t = rules.thresholds
    sup = rules.support
    was = band(rules, state)
    s = replace(state, score=new_score(rules, state.score, result), attempts=state.attempts + 1)

    if first_try_correct:
        s = replace(s, correct_streak=s.correct_streak + 1, wrong_streak=0)
        if s.correct_streak % sup.up_after_correct == 0:
            s = replace(s, support_level=_move_support(rules, s.support_level, +1))
    else:
        s = replace(s, wrong_streak=s.wrong_streak + 1, correct_streak=0)
        if s.wrong_streak % sup.down_after_wrong == 0:
            s = replace(s, support_level=_move_support(rules, s.support_level, -1))

    # Falling from practice into reteach: teach again with full support.
    if was == "practice" and band(rules, s) == "reteach":
        s = replace(s, support_level=sup.start["reteach"])

    if (not s.mastered and s.score >= t.mastered_at and s.attempts >= t.min_attempts
            and s.correct_streak >= t.last_correct):
        s = review.start_review(s, rules, today)
    return s
