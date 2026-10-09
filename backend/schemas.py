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


class Learner(BaseModel):
    id: str
    name: str
    picture: str
    profile: str
    interests: list[str]


class GroupIn(BaseModel):
    tutor_name: str
    learners: list[LearnerIn]


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
    story_id: str
    question_index: int            # 0-based, in the order of StoryOut.questions
    choice: str


class QuizResult(BaseModel):
    correct: int                   # first answers that were right
    total: int
    story_level_before: int
    story_level: int               # the level of the next story (rules.json story_quiz)


class StoryAnswerOut(BaseModel):
    correct: bool
    mistake_type: Optional[str]    # C_LITERAL, C_SEQUENCE or C_INFER when wrong
    feedback: "Feedback"
    quiz: Optional[QuizResult]     # set once every question has a first answer; the next story is queued then


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


class SheetOut(BaseModel):
    name: str
    date: str
    words: list[SheetWord]
    sentence: str
    home_line_fil: str


class ApprovalItem(BaseModel):
    id: str
    kind: str
    child_id: Optional[str]
    payload: dict


class ApprovalIn(BaseModel):
    approve: bool
