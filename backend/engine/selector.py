"""Choose the next item for a learner. All numbers come from rules.json.

Skill: a due review skill first, else the weakest unlocked skill (rules.selection.skill_order).
Then task type, item, distractor tiles and prefill. Comprehension skills are not chosen here:
they are practiced in the story turn.
"""
import random
from dataclasses import dataclass, replace
from datetime import date
from typing import Optional, Sequence, Union

from backend.content import Content, Sentence, Skill, Word
from backend.engine import review
from backend.engine.state import SkillState, new_state

Entry = Union[Word, Sentence]


@dataclass
class Pick:
    skill_id: str
    task_type: str
    item_id: str
    answer: list[str]      # what `given` must equal (one entry per slot)
    tiles: list[str]       # tiles to choose from, shuffled
    syllables: list[str]
    prefill: list[str]     # one entry per slot; "" = empty slot
    support_level: str
    is_review: bool
    is_easy: bool
    gap_slot: Optional[int] = None   # missing_letter: the box the learner fills


# ---------- skills ----------

def _uses(content: Content, skill: Skill) -> set[str]:
    task_ids = content.rules.selection.task_types_by_category.get(skill.category, [])
    return {t.uses for t in content.data.task_types if t.id in task_ids}


def skill_items(content: Content, skill: Skill) -> list[Entry]:
    """Tile-turn items for a skill: words/syllables, or sentences, depending on its task types."""
    uses = _uses(content, skill)
    items: list[Entry] = []
    if "words" in uses:
        items += [w for w in content.data.words if skill.id in w.skill_ids]
    if "sentences" in uses:
        items += [s for s in content.sentences if skill.id in s.skill_ids]
    return items


def tile_skills(content: Content) -> list[Skill]:
    return [s for s in content.skills if skill_items(content, s)]


def _state(states: dict[str, SkillState], skill_id: str, rules) -> SkillState:
    return states.get(skill_id) or new_state(skill_id, rules)


def is_unlocked(skill: Skill, states: dict[str, SkillState]) -> bool:
    return all(p in states and states[p].mastered for p in skill.prerequisites)


def due_review_skill(content: Content, states: dict[str, SkillState], today: date) -> Optional[Skill]:
    due = [s for s in tile_skills(content) if s.id in states and review.is_due(states[s.id], today)]
    return min(due, key=lambda s: (states[s.id].next_review_at, s.order), default=None)


def weakest_unlocked_skill(content: Content, states: dict[str, SkillState], words_only: bool = False) -> Skill:
    """Lowest score among unlocked, not mastered skills that have items; ties go to the lower order."""
    rules = content.rules
    skills = tile_skills(content)
    if words_only:
        skills = [s for s in skills if any(isinstance(i, Word) for i in skill_items(content, s))]
    open_ = [s for s in skills if is_unlocked(s, states) and not _state(states, s.id, rules).mastered]
    candidates = open_ or skills
    return min(candidates, key=lambda s: (_state(states, s.id, rules).score, s.order))


def choose_skill(content: Content, states: dict[str, SkillState], today: date) -> tuple[Skill, bool]:
    """(skill, is_review)."""
    for rule in content.rules.selection.skill_order:
        if rule == "due_review":
            skill = due_review_skill(content, states, today)
            if skill:
                return skill, True
        elif rule == "weakest_unlocked":
            return weakest_unlocked_skill(content, states), False
    return weakest_unlocked_skill(content, states), False


# ---------- difficulty ----------

def difficulty(first_try_results: list[bool], rules) -> str:
    """easy / normal / hard from accuracy over the last `window` items (needs a full window)."""
    d = rules.difficulty
    recent = first_try_results[-d.window:]
    if len(recent) < d.window:
        return "normal"
    accuracy = sum(recent) / len(recent)
    if accuracy > d.harder_above:
        return "hard"
    if accuracy < d.easier_below:
        return "easy"
    return "normal"


def _size(item: Entry) -> int:
    return len(item.syllables) if isinstance(item, Word) else len(item.word_tiles)


def choose_item(items: list[Entry], used: Sequence[str], level: str, prefer: Sequence[str] = ()) -> Entry:
    """Unused items first. easy = fewest syllables, hard = most, normal = content order.
    used: item ids oldest first. When every item was used, the one seen longest ago comes back.
    prefer: word texts from the learner's interests (content.json interests[].words); used first when unused."""
    last_seen = {item_id: k for k, item_id in enumerate(used)}
    pool = [i for i in items if i.id not in last_seen]
    if not pool:
        return min(items, key=lambda i: last_seen[i.id])
    liked = [i for i in pool if getattr(i, "text", None) in set(prefer)]
    pool = liked or pool
    if level == "easy":
        return min(pool, key=_size)
    if level == "hard":
        return max(pool, key=_size)
    return pool[0]


# ---------- task type and tiles ----------

def _gap(word: Word, skill: Skill) -> int:
    """The slot left empty in missing_letter: the first tile from the skill's letters, else the last tile."""
    for i, t in enumerate(word.tiles):
        if t in skill.letters:
            return i
    return len(word.tiles) - 1


def _task_fits(task_type: str, item: Entry, content: Content) -> bool:
    uses = next(t.uses for t in content.data.task_types if t.id == task_type)
    if isinstance(item, Sentence):
        return uses == "sentences"
    if uses != "words":
        return False
    if task_type == "dictation_syllables":
        return len(item.syllables) >= 2
    return True


def choose_task_type(content: Content, skill: Skill, state: SkillState, item: Entry) -> str:
    """Rotate through the category's task types that fit the item."""
    options = [t for t in content.rules.selection.task_types_by_category[skill.category]
               if _task_fits(t, item, content)]
    return options[state.attempts % len(options)]


def letter_distractors(word: Word, rules, count: int, exclude: tuple[str, ...] = ()) -> list[str]:
    """Distractor letter tiles. Words with ng always get n and g."""
    ng = rules.confusable_letters.ng
    has_ng = "ng" in word.tiles
    candidates = (list(ng) if has_ng else []) + list(word.distractor_tiles)
    pairs = rules.confusable_letters.vowels + rules.confusable_letters.consonants
    for tile in word.tiles:
        for a, b in pairs:
            if tile in (a, b):
                candidates.append(b if tile == a else a)
    # Fill up with other letters from the confusable lists that are not in the word.
    candidates += [letter for pair in pairs for letter in pair if letter not in word.tiles]
    out = []
    for t in candidates:
        if t not in out and t not in exclude:
            out.append(t)
    return out[:max(count, len(ng) if has_ng else 0)]


def syllable_distractors(word: Word, items: list[Entry], count: int) -> list[str]:
    """Syllables from other items of the same skill (real content, never made up)."""
    out = []
    for item in items:
        if isinstance(item, Word) and item.id != word.id:
            for syl in item.syllables:
                if syl not in word.syllables and syl not in out:
                    out.append(syl)
    return out[:count]


def _prefill(answer: list[str], support_level: str) -> list[str]:
    if support_level == "show":
        return list(answer)
    if support_level == "guide":
        return answer[:1] + [""] * (len(answer) - 1)
    return [""] * len(answer)


def build_pick(content: Content, skill: Skill, state: SkillState, item: Entry, level: str,
               is_review: bool, is_easy: bool, rng: random.Random, task_type: Optional[str] = None) -> Pick:
    """task_type: a re-teach method's task type (rules.json reteach.effects), used when it fits the item."""
    rules = content.rules
    if task_type and task_type in rules.selection.task_types_by_category[skill.category] \
            and _task_fits(task_type, item, content):
        task = task_type
    else:
        task = choose_task_type(content, skill, state, item)
    count = rules.difficulty.distractor_tiles[level]
    syllables = item.syllables if isinstance(item, Word) else []
    gap = None

    if task == "sentence_builder":
        answer, tiles = list(item.word_tiles), list(item.word_tiles)
        prefill = _prefill(answer, state.support_level)
    elif task == "dictation_syllables":
        answer = list(item.syllables)
        tiles = answer + syllable_distractors(item, skill_items(content, skill), count)
        prefill = _prefill(answer, state.support_level)
    elif task == "missing_letter":
        answer = list(item.tiles)
        gap = _gap(item, skill)
        tiles = [item.tiles[gap]] + letter_distractors(item, rules, count, exclude=(item.tiles[gap],))
        prefill = list(answer) if state.support_level == "show" else [
            "" if i == gap else t for i, t in enumerate(answer)]
    else:  # dictation_letters
        answer = list(item.tiles)
        tiles = answer + letter_distractors(item, rules, count)
        prefill = _prefill(answer, state.support_level)

    rng.shuffle(tiles)
    return Pick(skill_id=skill.id, task_type=task, item_id=item.id, answer=answer, tiles=tiles,
                syllables=syllables, prefill=prefill, support_level=state.support_level,
                is_review=is_review, is_easy=is_easy, gap_slot=gap)


def pick_next(content: Content, states: dict[str, SkillState], today: date, used: Sequence[str],
              first_try_results: list[bool], easy: bool = False,
              rng: Optional[random.Random] = None, prefer: Sequence[str] = (),
              method: Optional[dict] = None) -> Pick:
    """The next item for one learner.

    easy=True (from rotation after wrong answers in a row, or a slow answer): one easy item from a mastered
    skill, or from the current skill at easy difficulty if nothing is mastered yet.
    prefer: word texts from the learner's interests. method: a running re-teach method
    ({"skill_id", "effect": rules.json reteach.effects[...]}): its skill, difficulty and task type.
    """
    rng = rng or random.Random()
    rules = content.rules
    task_type = None
    if method is not None:
        skill = next(s for s in content.data.skills if s.id == method["skill_id"])
        is_review = False
        level = method["effect"].get("difficulty", difficulty(first_try_results, rules))
        task_type = method["effect"].get("task_type")
    elif easy:
        mastered = [s for s in tile_skills(content) if _state(states, s.id, rules).mastered]
        skill = mastered[0] if mastered else weakest_unlocked_skill(content, states)
        is_review, level = False, "easy"
    else:
        skill, is_review = choose_skill(content, states, today)
        level = difficulty(first_try_results, rules)
    state = _state(states, skill.id, rules)
    if method is not None and method.get("support") and state.support_level == "alone":
        state = replace(state, support_level=method["support"])     # re-teach: some help again
    item = choose_item(skill_items(content, skill), used, level, prefer)
    return build_pick(content, skill, state, item, level, is_review, easy, rng, task_type)
