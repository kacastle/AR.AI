"""Review dates after mastery, and the placement test. All numbers come from rules.json."""
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Optional

from backend.engine.state import SkillState, new_state


# ---------- review ----------

def start_review(state: SkillState, rules, today: date) -> SkillState:
    """Called when a skill becomes mastered: the first review is days[0] from today."""
    return replace(state, mastered_at=today, review_step=0,
                   next_review_at=today + timedelta(days=rules.review.days[0]))


def is_due(state: SkillState, today: date) -> bool:
    return state.mastered and state.next_review_at is not None and state.next_review_at <= today


def apply_review(state: SkillState, correct: bool, rules, today: date) -> SkillState:
    """A correct review moves to the next step; after the last step no more reviews.
    A wrong review sets the score to fail_score, puts the skill back in practice, and restarts the steps."""
    if correct:
        step = state.review_step + 1
        if step < len(rules.review.days):
            return replace(state, review_step=step, next_review_at=today + timedelta(days=rules.review.days[step]))
        return replace(state, review_step=None, next_review_at=None)
    return replace(state, score=rules.review.fail_score, mastered_at=None, review_step=None,
                   next_review_at=None, support_level=rules.support.start["practice"])


# ---------- placement ----------

@dataclass
class PlacementResult:
    done: bool
    passed: list[str]
    failed: list[str]
    start_skill: Optional[str]   # practice starts at the first failed skill
    profile: Optional[str]       # set when done


def _skill_passed(results: list[bool], rules) -> bool:
    # A placement skill passes when every one of its items is correct.
    return len(results) >= rules.placement.items_per_skill and all(results[:rules.placement.items_per_skill])


def placement_status(answers: dict[str, list[bool]], rules) -> PlacementResult:
    """answers: skill_id -> results of that skill's placement items, in the order they were given."""
    p = rules.placement
    passed, failed, fails_in_row = [], [], 0
    for skill_id in p.skills:
        results = answers.get(skill_id, [])
        if len(results) < p.items_per_skill:
            return PlacementResult(False, passed, failed, failed[0] if failed else None, None)
        if _skill_passed(results, rules):
            passed.append(skill_id)
            fails_in_row = 0
        else:
            failed.append(skill_id)
            fails_in_row += 1
            if fails_in_row >= p.stop_after_failed_skills:
                break
    before = p.skills[:p.skills.index(p.low_emergent_if_fail_before)]
    low, high = p.profiles[0], p.profiles[1]
    profile = low if any(s in before for s in failed) else high
    return PlacementResult(True, passed, failed, failed[0] if failed else None, profile)


def next_placement_skill(answers: dict[str, list[bool]], rules) -> Optional[str]:
    """The skill to give the next placement item for, or None when placement is finished."""
    status = placement_status(answers, rules)
    if status.done:
        return None
    for skill_id in rules.placement.skills:
        if len(answers.get(skill_id, [])) < rules.placement.items_per_skill:
            return skill_id
    return None


def placement_states(result: PlacementResult, rules, today: date) -> list[SkillState]:
    """Passed skills start at passed_score. They count as mastered so that practice can start at the
    first failed skill (its prerequisites must be mastered to unlock it). No review dates for them."""
    return [replace(new_state(s, rules), score=rules.placement.passed_score,
                    support_level=rules.support.start["practice"], mastered_at=today)
            for s in result.passed]
