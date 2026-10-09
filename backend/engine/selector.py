"""Item selection.

P2-1 stub: the first skill (by `order`) that the child has not mastered and that has
words, then the first word of that skill not used yet in this session. The real
selector (due reviews, weakest unlocked skill, difficulty) replaces this later.
"""
from backend.content import Content, Skill, Word


def skill_words(content: Content, skill_id: str) -> list[Word]:
    return [w for w in content.data.words if w.kind == "word" and skill_id in w.skill_ids]


def focus_skill(content: Content, mastered: set[str]) -> Skill:
    for s in content.skills:
        if s.id not in mastered and skill_words(content, s.id):
            return s
    return content.skills[0]


def pick_word(content: Content, mastered: set[str], used: set[str]) -> tuple[Skill, Word]:
    for s in content.skills:
        if s.id in mastered:
            continue
        for w in skill_words(content, s.id):
            if w.id not in used:
                return s, w
    # Everything used: start again from the focus skill.
    s = focus_skill(content, mastered)
    return s, skill_words(content, s.id)[0]
