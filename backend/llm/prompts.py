"""The four prompts from content/prompts.md, as parsed by content/test_prompts.py (no second copy).

The harness reads each section's System and User blocks from prompts.md; its case builders fill the
values (plot, object, word bank, limits from rules.json, JSON schema). This module only gives the backend
one place to get them.
"""
from backend.llm.harness import tp

# Temperature and num_predict per prompt (prompts.md section 0 table).
SETTINGS = tp.SETTINGS_BY_KIND

story_case = tp.story_case       # (learner, rnd) -> values for the personal story prompt
words_case = tp.words_case       # (learner, rnd) -> values for the practice words prompt
lesson_case = tp.lesson_case     # (learner + lesson_skill, rnd) -> values for the mini lesson story prompt


def build(kind: str, values: dict) -> tuple[str, str, list[str]]:
    """(system, user, unfilled placeholders) for one prompt. Values starting with _ are for the checks."""
    user, unfilled = tp.fill(tp.TEMPLATES[kind], {k: v for k, v in values.items() if not k.startswith("_")})
    system = tp.SYSTEM if kind == "story" else tp.GENERIC_SYSTEM
    return system, user, unfilled
