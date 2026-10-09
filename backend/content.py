"""Load and validate content/content.json and content/rules.json.

Run `python -m backend.content` to check the files. It prints OK or a numbered
list of problems for Person 3 and exits 1 if there are problems.
"""
import json
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, ValidationError

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


class Model(BaseModel):
    # Allow new fields from Person 3; a missing or renamed field is still an error.
    model_config = ConfigDict(extra="allow")


# ---------- content.json ----------

class Skill(Model):
    id: str
    order: int
    category: str
    name_fil: str
    name_en: str
    level: int
    letters: list[str]
    prerequisites: list[str]
    mistake_types: list[str]
    core: bool


class Word(Model):
    id: str
    kind: str
    text: str
    syllables: list[str]
    tiles: list[str]
    skill_ids: list[str]
    level: int
    tts_text: str
    meaning_en: Optional[str]  # null for syllables
    distractor_tiles: list[str]


class Sentence(Model):
    id: str
    text: str
    word_tiles: list[str]
    skill_ids: list[str]
    level: int


class Question(Model):
    id: Optional[str] = None
    type: str
    skill_id: str
    prompt: str
    choices: list[str]
    answer: str


class Story(Model):
    id: str
    title: str
    level: int
    skill_ids: list[str]
    target_word_ids: list[str]
    interests: list[str]
    word_count: int
    paragraphs: list[str]
    questions: list[Question]
    source: str
    reviewed: bool
    approved_by_tutor: bool


class TaskType(Model):
    id: str
    input: str
    uses: str
    tts: bool
    min_level: int


class Interest(Model):
    id: str
    label_fil: str
    label_en: str
    icon: str
    words: list[str]
    objects: list[str]


class StoryTemplate(Model):
    id: str
    level: int
    title: str
    skill_ids: list[str]
    paragraphs: list[str]
    questions: list[Question]


class StoryPlot(Model):
    id: str
    level: int
    characters: list[str]
    outline_en: str


class ContentFile(Model):
    version: str
    language: str
    levels: list[int]
    skills: list[Skill]
    words: list[Word]
    sentences: list[Sentence]
    stories: list[Story]
    task_types: list[TaskType]
    interests: list[Interest]
    story_templates: list[StoryTemplate]
    story_plots: list[StoryPlot]


# ---------- rules.json ----------

class Score(Model):
    alpha: float
    start_score: float
    result_values: dict[str, float]


class Thresholds(Model):
    reteach_below: float
    mastered_at: float
    min_attempts: int
    last_correct: int


class Support(Model):
    levels: list[str]
    up_after_correct: int
    down_after_wrong: int
    start: dict[str, str]
    prefill: dict[str, str]


class Difficulty(Model):
    window: int
    target_low: float
    target_high: float
    harder_above: float
    easier_below: float
    stop_after_wrong: int
    distractor_tiles: dict[str, int]


class Review(Model):
    days: list[int]
    fail_score: float


class Hints(Model):
    ladder: list[str]
    max_attempts: int
    after_max: str


class Timing(Model):
    slow_seconds: int
    item_seconds: int


class Selection(Model):
    skill_order: list[str]
    task_types_by_category: dict[str, list[str]]
    avoid_items_seen_in_last_sessions: int


class Rotation(Model):
    order: str
    skip_absent: bool
    easy_item_after_wrong: int


class DemoFast(Model):
    phase_minutes: int
    item_seconds: int


class SessionRules(Model):
    max_minutes: int
    tile_turn_minutes: int
    story_turn_minutes: int
    summary_minutes: int
    demo_fast: DemoFast


class Placement(Model):
    items_per_skill: int
    stop_after_failed_skills: int
    passed_score: float
    skills: list[str]
    low_emergent_if_fail_before: str
    profiles: list[str]


class ConfusableLetters(Model):
    vowels: list[list[str]]
    consonants: list[list[str]]
    ng: list[str]


class MistakeType(Model):
    group: str
    description_en: str
    method: str


class Method(Model):
    description_en: str
    items_after: int


class FeedbackTemplate(Model):
    message_fil: list[str]
    hint_fil: Optional[str]


class PracticeSheet(Model):
    words: int
    sentences: int
    home_line_fil: str


class Safety(Model):
    blocklist: list[str]


class RulesFile(Model):
    version: str
    score: Score
    thresholds: Thresholds
    support: Support
    difficulty: Difficulty
    hints: Hints
    review: Review
    timing: Timing
    selection: Selection
    session: SessionRules
    rotation: Rotation
    placement: Placement
    confusable_letters: ConfusableLetters
    mistake_types: dict[str, MistakeType]
    methods: dict[str, Method]
    feedback_templates: dict[str, FeedbackTemplate]
    practice_sheet: PracticeSheet
    safety: Safety
    personalization: dict


# ---------- loading ----------

class Content:
    """Validated content plus lookups and the list of problems found."""

    def __init__(self, data: ContentFile, rules: RulesFile, problems: list[str]):
        self.data = data
        self.rules = rules
        self.problems = problems
        self.skills = sorted(data.skills, key=lambda s: s.order)
        self.skills_by_id = {s.id: s for s in data.skills}
        self.words_by_id = {w.id: w for w in data.words}
        self.stories_by_id = {s.id: s for s in data.stories}
        self.sentences = data.sentences


class ContentError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__(f"{len(problems)} content problem(s)")
        self.problems = problems


def _pydantic_problems(file: str, raw: dict, err: ValidationError) -> list[str]:
    problems = []
    for e in err.errors():
        loc = e["loc"]
        where = file
        if len(loc) >= 2 and isinstance(loc[1], int):
            item = raw.get(loc[0], [])[loc[1]] if isinstance(raw.get(loc[0]), list) else {}
            item_id = item.get("id") if isinstance(item, dict) else None
            where += f" {loc[0]}[{loc[1]}]" + (f" ({item_id})" if item_id else "")
            rest = loc[2:]
        else:
            rest = loc
        field = ".".join(str(p) for p in rest) or "(whole item)"
        if e["type"] == "missing":
            problems.append(f"{where}: field '{field}' is missing")
        else:
            problems.append(f"{where}: field '{field}': {e['msg']} (got {e.get('input')!r})")
    return problems


def _cross_check(c: ContentFile, r: RulesFile) -> list[str]:
    p = []
    skill_ids = {s.id for s in c.skills}
    word_ids = {w.id for w in c.words}
    task_ids = {t.id for t in c.task_types}

    for name, items in [("skills", c.skills), ("words", c.words), ("sentences", c.sentences),
                        ("stories", c.stories), ("task_types", c.task_types), ("interests", c.interests)]:
        seen = set()
        for it in items:
            if it.id in seen:
                p.append(f"content.json {name}: duplicate id '{it.id}'")
            seen.add(it.id)

    for s in c.skills:
        for pre in s.prerequisites:
            if pre not in skill_ids:
                p.append(f"content.json skill {s.id}: prerequisite '{pre}' is not a skill id")
        for m in s.mistake_types:
            if m not in r.mistake_types:
                p.append(f"content.json skill {s.id}: mistake type '{m}' is not in rules.json mistake_types")

    for w in c.words:
        if "".join(w.tiles) != w.text:
            p.append(f"content.json word {w.id}: tiles {'+'.join(w.tiles)} do not spell '{w.text}'")
        if "".join(w.syllables) != w.text:
            p.append(f"content.json word {w.id}: syllables {'-'.join(w.syllables)} do not spell '{w.text}'")
        for i in range(len(w.tiles) - 1):
            if w.tiles[i] == "n" and w.tiles[i + 1] == "g":
                p.append(f"content.json word {w.id}: 'n','g' are separate tiles; ng must be one tile")
        for sk in w.skill_ids:
            if sk not in skill_ids:
                p.append(f"content.json word {w.id}: skill '{sk}' is not a skill id")

    for sn in c.sentences:
        if " ".join(sn.word_tiles) != sn.text:
            p.append(f"content.json sentence {sn.id}: word_tiles do not match text '{sn.text}'")
        for sk in sn.skill_ids:
            if sk not in skill_ids:
                p.append(f"content.json sentence {sn.id}: skill '{sk}' is not a skill id")

    for st in c.stories:
        for sk in st.skill_ids:
            if sk not in skill_ids:
                p.append(f"content.json story {st.id}: skill '{sk}' is not a skill id")
        for wid in st.target_word_ids:
            if wid not in word_ids:
                p.append(f"content.json story {st.id}: target word '{wid}' is not a word id")
        count = len(" ".join(st.paragraphs).split())
        if count != st.word_count:
            p.append(f"content.json story {st.id}: word_count is {st.word_count} but the paragraphs have {count} words")
        for q in st.questions:
            if q.answer not in q.choices:
                p.append(f"content.json story {st.id} question {q.id}: answer '{q.answer}' is not in choices")

    for cat, tasks in r.selection.task_types_by_category.items():
        for t in tasks:
            if t not in task_ids:
                p.append(f"rules.json selection.task_types_by_category.{cat}: '{t}' is not a task type id")
    for sk in r.placement.skills:
        if sk not in skill_ids:
            p.append(f"rules.json placement.skills: '{sk}' is not a skill id")
    if r.placement.low_emergent_if_fail_before not in r.placement.skills:
        p.append(f"rules.json placement.low_emergent_if_fail_before: "
                 f"'{r.placement.low_emergent_if_fail_before}' is not in placement.skills")
    for code, mt in r.mistake_types.items():
        if mt.method not in r.methods:
            p.append(f"rules.json mistake_types.{code}: method '{mt.method}' is not in methods")
        if code not in r.feedback_templates:
            p.append(f"rules.json feedback_templates: no template for mistake type '{code}'")
    for key in ("CORRECT", "SHOW_ANSWER"):
        if key not in r.feedback_templates:
            p.append(f"rules.json feedback_templates: '{key}' is missing")
    return p


def load_content(content_dir: Path = CONTENT_DIR) -> Content:
    """Load both files. Raises ContentError if they cannot be read into the models."""
    problems = []
    raw = {}
    for name in ("content.json", "rules.json"):
        try:
            raw[name] = json.loads((content_dir / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{name}: cannot read file: {e}")
    if problems:
        raise ContentError(problems)

    parsed = {}
    for name, model in (("content.json", ContentFile), ("rules.json", RulesFile)):
        try:
            parsed[name] = model.model_validate(raw[name])
        except ValidationError as e:
            problems += _pydantic_problems(name, raw[name], e)
    if problems:
        raise ContentError(problems)

    c, r = parsed["content.json"], parsed["rules.json"]
    return Content(c, r, _cross_check(c, r))


def format_problems(problems: list[str]) -> str:
    return "\n".join(f"{i}. {line}" for i, line in enumerate(problems, 1))


def main() -> int:
    try:
        content = load_content()
    except ContentError as e:
        print(f"Content cannot be loaded ({len(e.problems)} problem(s)):")
        print(format_problems(e.problems))
        return 1
    d = content.data
    if content.problems:
        print(f"Content loaded with {len(content.problems)} problem(s):")
        print(format_problems(content.problems))
        return 1
    print(f"OK ({len(d.skills)} skills, {len(d.words)} words, {len(d.sentences)} sentences, "
          f"{len(d.stories)} stories)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
