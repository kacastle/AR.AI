"""Mistake code for a wrong answer, and the fixed feedback text for it (rules.json feedback_templates).

Placeholders are filled from the item (rules.md section 8). Codes without a template get GENERIC.
The model is never called here: this runs inside a turn.
"""
from typing import Optional

from backend.engine.classifier import classify
from backend.schemas import Feedback

GENERIC = "Subukan natin ulit, {name}!"


def _plain(tile: str) -> str:
    return tile.lower().rstrip(".?!")


def mistake_code(task_type: str, expected: list[str], given: list[str]) -> Optional[str]:
    """None when correct. Sentences (word tiles) get SN_ codes, everything else the tile classifier."""
    if given == expected:
        return None
    if task_type == "sentence_builder":
        if [_plain(t) for t in given] == [_plain(t) for t in expected]:
            return "SN_PUNCT"
        return "SN_ORDER"
    return classify(expected, given)


def feedback_for(rules, code: str, name: str, syllables: list[str], slots: int,
                 turn: int = 0, with_hint: bool = True) -> Feedback:
    """code: a mistake code, CORRECT or SHOW_ANSWER. turn picks which message_fil line (they rotate)."""
    values = {
        "name": name,
        "syllables_hyphen": "-".join(syllables),
        "syllables_last_caps": "-".join(syllables[:-1] + [s.upper() for s in syllables[-1:]]),
        "slots": slots,
    }
    template = rules.feedback_templates.get(code)
    if template is None:
        return Feedback(message_fil=GENERIC.format(**values), hint_fil=None)
    lines = template.message_fil
    hint = template.hint_fil.format(**values) if with_hint and template.hint_fil else None
    return Feedback(message_fil=lines[turn % len(lines)].format(**values), hint_fil=hint)
