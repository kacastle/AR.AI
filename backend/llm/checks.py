"""Checks on every model output, from content/test_prompts.py (Person 3's checks; no second copy).

Story (check_story), with the limits from rules.json story_levels:
  JSON parses with title, paragraphs, questions | paragraph count | word count in range |
  sentence count | no sentence longer than max_words_per_sentence (level 1: 8, level 2: 12) |
  the learner's name at least min_name_mentions times, never tacked on after a comma |
  the interest object in the first and the last paragraph | no other names | 3 questions of the chosen types,
  each with 3 different choices and the answer one of them | answers found in the story |
  no English words | nothing from safety.blocklist.
  Target words are optional (rules.json personalization.personal_story.target_words), so they are not required.
Words (check_words): exact count, no duplicates, only candidate words, no blocklist.
Summary (check_summary): the present child_ids, real skill ids and methods, numbers match,
  25 words or fewer, no ids in the text, no percentages, group note when needed, not judgmental, no blocklist.
"""
from typing import Optional

from backend.llm.harness import tp


def check(kind: str, out: str, values: dict, learner: Optional[dict]) -> tuple[list[str], Optional[dict]]:
    """(failed check labels, parsed JSON). No labels = the output passed."""
    if kind == "story":
        return tp.check_story(out, values, learner)
    if kind == "words":
        return tp.check_words(out, values)
    if kind == "summary":
        return tp.check_summary(out, values)
    if kind == "lesson":
        return tp.check_lesson(out, values, learner)
    raise ValueError(f"no checks for {kind!r}")
