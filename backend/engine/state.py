"""One learner's state for one skill (a row of the skill_state table)."""
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class SkillState:
    skill_id: str
    score: float
    support_level: str
    attempts: int = 0
    correct_streak: int = 0
    wrong_streak: int = 0
    review_step: Optional[int] = None      # index into rules.review.days; None = not in review
    next_review_at: Optional[date] = None
    mastered_at: Optional[date] = None

    @property
    def mastered(self) -> bool:
        return self.mastered_at is not None


def new_state(skill_id: str, rules) -> SkillState:
    return SkillState(skill_id=skill_id, score=rules.score.start_score,
                      support_level=rules.support.start["new"])
