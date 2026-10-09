"""Request and response shapes for the API. See backend/API_CONTRACT.md."""
from typing import Literal, Optional

from pydantic import BaseModel

SupportLevel = Literal["show", "guide", "alone"]
Phase = Literal["tiles", "stories", "summary"]
NextAction = Literal["retry", "show_answer", "next"]
HintKind = Literal["replay_by_syllable", "highlight_slot", "first_tile"]


class LoginIn(BaseModel):
    pin: str


class OkOut(BaseModel):
    ok: bool


class LearnerIn(BaseModel):
    name: str
    picture: str
    profile: str
    interests: list[str] = []      # ids from content.json interests, at most rules.personalization max
    diagnostic: bool = False       # true: short placement items first (rules.json placement), then practice


class Learner(BaseModel):
    id: str
    name: str
    picture: str
    profile: str
    interests: list[str]


class GroupIn(BaseModel):
    tutor_name: str
    learners: list[LearnerIn] = []
    existing_child_ids: list[str] = []   # returning learners (GET /api/learners): progress and diagnostic kept


class LearnerListItem(BaseModel):
    id: str
    name: str
    picture: str
    interests: list[str]
    placement: Optional[str]       # pending, done, or null (no diagnostic)
    story_level: int
    current_skill_fil: str
    mastered_count: int
    last_session: Optional[str]    # YYYY-MM-DD of the learner's last answered item


class Group(BaseModel):
    id: str
    tutor_name: str
    learners: list[Learner]


class SessionIn(BaseModel):
    group_id: str
    present: list[str]


class Session(BaseModel):
    id: str
    group_id: str
    present: list[str]
    phase: Phase
    read_along_story_id: str
    story_ids: dict[str, str]      # child_id -> the story that learner reads in the story turn


class StoryWord(BaseModel):
    text: str
    start_ms: int
    end_ms: int


class StoryQuestion(BaseModel):
    type: str                      # who, what, where, sequence, feeling, main_idea
    prompt: str
    choices: list[str]             # the answer is checked by POST /api/sessions/{id}/story_answer


class StoryOut(BaseModel):
    title: str
    paragraphs: list[str]
    words: list[StoryWord]
    audio_url: str
    questions: list[StoryQuestion] = []


class StoryAnswerIn(BaseModel):
    child_id: str
    question_id: str               # StoryTurn.question.id ("{story_id}:{index}")
    choice: str
    attempt: int = 1               # 1, then 2 after a wrong first answer (the second wrong answer shows it)


class QuizResult(BaseModel):
    correct: int                   # first answers that were right
    total: int
    story_level_before: int
    story_level: int               # the level of the next story (rules.json story_quiz)


class StoryAnswerOut(BaseModel):
    correct: bool
    mistake_type: Optional[str]    # C_LITERAL, C_SEQUENCE or C_INFER when wrong
    feedback: "Feedback"
    next_action: Literal["retry", "next"]
    answer: Optional[str]          # the right choice, after the second wrong answer
    quiz: Optional[QuizResult]     # set once every question has a first answer; the next story is queued then


class StoryTurnQuestion(BaseModel):
    id: str                        # "{story_id}:{index}"
    type: str
    prompt: str
    choices: list[str]
    prompt_audio: Optional[str]


class StoryTurn(BaseModel):
    """One question of one learner's quiz on that learner's own story (session.story_ids)."""
    child_id: str
    child_name: str
    story_id: str
    turn_number: int               # the question number in this learner's quiz, from 1
    questions_total: int
    question: StoryTurnQuestion


class PhaseIn(BaseModel):
    phase: Phase


class PhaseOut(BaseModel):
    phase: Phase
    ends_at: str


class Item(BaseModel):
    id: str
    prompt_audio: str
    slots: int
    tiles: list[str]
    syllables: list[str]


class LessonExample(BaseModel):
    text: str
    tiles: list[str]
    syllables: list[str]
    highlight: list[int]           # tile indexes to light up (the skill's letters, or the part it is about)


class LessonWord(BaseModel):
    text: str
    syllables: list[str]


class LessonStory(BaseModel):
    sentences: list[str]
    words: list[str]               # words of the skill to light up in the sentences
    source: str                    # model (a checked, approved lesson story) or content


class LessonLetter(BaseModel):
    letter: str
    audio: str                     # the letter's sound (/api/audio/syl_a.wav; a consonant with a: syl_ma)
    word: str                      # a word that starts with the letter (the learner's interest words first)
    word_audio: Optional[str]
    syllables: list[str]


class Lesson(BaseModel):
    """Shown before the item: teach first, then practise (backend/lessons.py)."""
    skill_id: str
    skill_name_fil: str
    skill_name_en: str
    reason: Literal["new", "reteach"]
    style: Literal["visual", "steps", "story", "letters"]
    example: LessonExample
    steps: list[str]               # the example built up: "ba", "bahay"
    more_words: list[LessonWord]
    story: Optional[LessonStory]   # set when style is story
    letters: list[LessonLetter] = []   # set when style is letters (letter_sound skills)


class InterestInfo(BaseModel):
    id: str
    label_fil: str
    label_en: str
    icon: str


class NextTurn(BaseModel):
    child_id: str
    child_name: str
    turn_number: int
    task_type: str
    item: Item
    support_level: SupportLevel
    prefill: list[str]
    gap_slot: Optional[int]
    seconds: int
    mode: Literal["placement", "reteach", "easy", "practice"] = "practice"
    method: Optional[str] = None           # running re-teach method (rules.json methods key)
    method_note: Optional[str] = None      # its description_en, for the tutor
    stars: int = 0
    streak: int = 0
    lesson: Optional[Lesson] = None        # teach before this item (a new skill, or re-teach another way)


class AnswerIn(BaseModel):
    child_id: str
    item_id: str
    given: list[str]
    hints_used: int
    attempt: int
    time_ms: int


class Feedback(BaseModel):
    message_fil: Optional[str]
    hint_fil: Optional[str]


class Hint(BaseModel):
    kind: HintKind
    audio: Optional[str]
    highlight_slot: Optional[int]


class Result(BaseModel):
    correct: bool
    mistake_type: Optional[str]
    feedback: Feedback
    hint: Optional[Hint]
    next_action: NextAction
    answer: Optional[list[str]]
    stars: int = 0                 # the learner's stars after this answer
    streak: int = 0
    method_started: Optional[str] = None   # a re-teach method that starts with the learner's next item
    mastered_skill: Optional[str] = None   # name_fil of a skill this answer mastered (celebrate it)


class LearnerSummary(BaseModel):
    child_id: str
    summary: str
    next_focus_skill: str
    next_method: str


class SummaryOut(BaseModel):
    learners: list[LearnerSummary]
    group_note: str


class SheetWord(BaseModel):
    text: str
    syllables: list[str]


class ParentNote(BaseModel):
    story_level: int
    level_label_fil: str           # rules.json practice_sheet.level_labels_fil
    current_skill_fil: str
    mastered_count: int
    total_skills: int


class SheetOut(BaseModel):
    name: str
    date: str
    words: list[SheetWord]
    sentence: str
    home_line_fil: str
    parent_note: Optional[ParentNote] = None


class ApprovalItem(BaseModel):
    id: str
    kind: str
    child_id: Optional[str]
    payload: dict


class ApprovalIn(BaseModel):
    approve: bool


class SkillScore(BaseModel):
    id: str
    name: str
    score: float


class InterestOut(BaseModel):
    id: str
    label: str
    icon: str


class MethodRun(BaseModel):
    mistake_type: str
    mistake: str
    method: str
    method_description: str
    correct: int
    total: int
    worked: Optional[bool]         # null while it runs


class SessionProgress(BaseModel):
    session_id: str
    date: str
    correct: int
    total: int


class HistoryPoint(BaseModel):
    session_id: str
    date: str                      # YYYY-MM-DD
    mastered_count: int
    avg_score: float
    accuracy: Optional[float]      # first tries right in that session (null when only story answers)


class LadderStep(BaseModel):
    skill_id: str
    name_fil: str
    level: int
    score: float
    mastered: bool


class ProfileOut(BaseModel):
    """Per-learner profile for the tutor and parents (backend/adapt.py profile())."""
    child_id: str
    name: str
    profile: str
    interests: list[InterestOut]
    diagnostic: Optional[str]      # null (none), "pending", "done"
    story_level: int
    pace: Optional[Literal["fast", "steady", "slow"]]
    current_skill: SkillScore
    mastered: list[SkillScore]
    strengths: list[SkillScore]
    needs_work: list[SkillScore]
    methods: list[MethodRun]
    stars: int
    streak: int
    sessions: list[SessionProgress]
    history: list[HistoryPoint] = []   # one point per session, oldest first (for the progress graph)
    ladder: list[LadderStep] = []      # every skill in content.json order (the reading ladder)
