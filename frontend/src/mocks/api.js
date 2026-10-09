// Offline mock of the backend in backend/API_CONTRACT.md. No network calls are made.
// Contract endpoints mirrored here:
//   POST /api/tutor/login             -> login(body)
//   GET  /api/groups/{id}             -> getGroup(groupId)
//   POST /api/sessions                -> createSession(body)
//   GET  /api/stories/{id}            -> getStory(storyId)
//   POST /api/sessions/{id}/phase     -> setPhase(sessionId, body)
//   GET  /api/sessions/{id}/next      -> getNextTurn(sessionId)
//   POST /api/sessions/{id}/answer    -> submitAnswer(sessionId, body)
//   GET  /api/sessions/{id}/summary   -> getSummary(sessionId)
//   GET  /api/children/{id}/sheet     -> getPracticeSheet(childId)
// Screens import src/api.js, which uses this file when VITE_USE_MOCK=true.
// NOT in the contract yet (proposal for the backend owner): getStoryTurn() and
// submitStoryAnswer() for the story questions in content.json `stories[].questions`.
// Shapes, hint ladder and feedback lines follow backend/main.py and content/rules.json.

export const DEMO_FAST = true
export const MOCK_GROUP_ID = 'g_mock'
export const MOCK_SESSION_ID = 's_mock'

// Example "Next turn" payload (GET /api/sessions/{id}/next).
export const mockNextTurnPayload = {
  child_id: 'c_ana',
  child_name: 'Ana',
  turn_number: 1,
  task_type: 'dictation_letters',
  item: {
    id: 'w_bata',
    prompt_audio: '/api/audio/w_bata.wav',
    slots: 4,
    tiles: ['t', 'a', 'd', 'b', 'a', 'p'],
    syllables: ['ba', 'ta'],
  },
  support_level: 'alone',
  prefill: ['', '', '', ''],
  seconds: 20,
}

// Example "Answer" request and result (POST /api/sessions/{id}/answer).
export const mockAnswerPayload = {
  request: {
    child_id: 'c_ana',
    item_id: 'w_bata',
    given: ['b', 'a', 't', 'a'],
    hints_used: 0,
    attempt: 1,
    time_ms: 4200,
  },
  response: {
    correct: true,
    mistake_type: null,
    feedback: { message_fil: 'Ang galing mo, Ana!', hint_fil: null },
    hint: null,
    next_action: 'next',
    answer: null,
  },
}

// Copied from content/rules.json.
const PHASE_MINUTES = DEMO_FAST
  ? { tiles: 1, stories: 1, summary: 1 }
  : { tiles: 35, stories: 15, summary: 10 }
const ITEM_SECONDS = DEMO_FAST ? 20 : 60
const HINT_LADDER = ['replay_by_syllable', 'highlight_slot', 'first_tile']
const FEEDBACK_TEMPLATES = {
  CORRECT: {
    message_fil: ['Ang galing mo, {name}!', 'Tama! Magaling, {name}!', 'Yehey! Tama ka!'],
    hint_fil: null,
  },
  SHOW_ANSWER: {
    message_fil: ['Tingnan ang tamang sagot.'],
    hint_fil: 'Ngayon, ikaw naman ang bumuo.',
  },
  C_LITERAL: {
    message_fil: ['Subukan natin ulit.'],
    hint_fil: 'Basahin ang may kulay na pangungusap.',
  },
}

// Skill names from content/content.json, for showing next_focus_skill.
export const SKILL_NAMES_FIL = {
  sk_vowels: 'Mga patinig: a, e, i, o, u',
  sk_ng: 'Ang titik ng',
  sk_cvc_final: 'Salitang nagtatapos sa katinig',
  sk_sentence_1: 'Simpleng pangungusap',
  sk_comp_literal: 'Sino, saan, ano',
}

const group = {
  id: MOCK_GROUP_ID,
  tutor_name: 'Teacher Liza',
  learners: [
    { id: 'c_ana', name: 'Ana', picture: 'cat', profile: 'low_emergent' },
    { id: 'c_ben', name: 'Ben', picture: 'dog', profile: 'high_emergent' },
    { id: 'c_mila', name: 'Mila', picture: 'star', profile: 'low_emergent' },
  ],
}

// From content/content.json `stories` (st_l1_001).
const stories = {
  st_l1_001: {
    title: 'Ang Bahay ni Ana',
    paragraphs: [
      'Si Ana ay may bahay. Malaki ang bahay ni Ana.',
      'May aso si Ana. Bantay ang pangalan ng aso.',
      'Masaya si Ana at si Bantay sa bahay.',
    ],
    questions: [
      { id: 'q_l1_001_1', type: 'who', prompt: 'Sino ang may aso?', choices: ['Ana', 'Ben', 'Lola'], answer: 'Ana' },
      { id: 'q_l1_001_2', type: 'what', prompt: 'Ano ang pangalan ng aso?', choices: ['Bantay', 'Muning', 'Tagpi'], answer: 'Bantay' },
      { id: 'q_l1_001_3', type: 'where', prompt: 'Saan masaya si Ana at si Bantay?', choices: ['sa bahay', 'sa ilog', 'sa paaralan'], answer: 'sa bahay' },
    ],
  },
}

// Tile items dealt in order: what /next returns plus the answer the server keeps to itself.
const items = [
  {
    task_type: 'dictation_letters',
    item: { id: 'w_bata', slots: 4, tiles: ['t', 'a', 'd', 'b', 'a', 'p'], syllables: ['ba', 'ta'] },
    support_level: 'alone',
    prefill: ['', '', '', ''],
    answer: ['b', 'a', 't', 'a'],
  },
  {
    task_type: 'dictation_syllables',
    item: { id: 'w_bahay', slots: 2, tiles: ['hay', 'lat', 'ba', 'ak'], syllables: ['ba', 'hay'] },
    support_level: 'guide',
    prefill: ['ba', ''],
    answer: ['ba', 'hay'],
  },
  {
    task_type: 'missing_letter',
    item: { id: 'w_aso', slots: 3, tiles: ['u', 'a', 'e', 'i'], syllables: ['a', 'so'] },
    support_level: 'alone',
    prefill: ['', 's', 'o'],
    answer: ['a', 's', 'o'],
  },
  {
    task_type: 'dictation_letters',
    item: { id: 'w_saging', slots: 5, tiles: ['g', 'ng', 's', 'n', 'a', 'k', 'i', 'g'], syllables: ['sa', 'ging'] },
    support_level: 'show',
    prefill: ['s', 'a', 'g', 'i', 'ng'],
    answer: ['s', 'a', 'g', 'i', 'ng'],
  },
  {
    task_type: 'sentence_builder',
    item: { id: 'sn_002', slots: 4, tiles: ['aso', 'Ben.', 'May', 'si'], syllables: [] },
    support_level: 'alone',
    prefill: ['', '', '', ''],
    answer: ['May', 'aso', 'si', 'Ben.'],
  },
]

const delay = (ms = 150) => new Promise((resolve) => setTimeout(resolve, ms))
const clone = (value) => JSON.parse(JSON.stringify(value))

let session = null
let turnNumber = 1
let storyRound = null
let events = []

function apiError(status, detail) {
  const error = new Error(detail)
  error.status = status
  error.detail = detail
  return error
}

function requireSession(sessionId) {
  if (!session || sessionId !== session.id) throw apiError(404, `session '${sessionId}' not found`)
}

const nameOf = (childId) => group.learners.find((l) => l.id === childId).name

function localIso(date) {
  const pad = (n) => String(Math.abs(n)).padStart(2, '0')
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(Math.trunc(offset / 60))}:${pad(offset % 60)}`
  )
}

export async function login(body) {
  await delay()
  if (typeof body?.pin !== 'string') throw apiError(422, 'pin is required')
  return { ok: true }
}

export async function getGroup(groupId) {
  await delay()
  if (groupId !== group.id) throw apiError(404, `group '${groupId}' not found`)
  return clone(group)
}

// Longer waits on session start and summary stand in for local AI work, so the loading
// screen shows in demos.
export async function createSession(body) {
  await delay(900)
  if (body.group_id !== group.id) throw apiError(404, `group '${body.group_id}' not found`)
  if (!body.present?.length) throw apiError(422, 'present must list at least one child id')
  const ids = new Set(group.learners.map((l) => l.id))
  const missing = body.present.filter((id) => !ids.has(id))
  if (missing.length) throw apiError(422, `not in this group: ${missing}`)
  session = {
    id: MOCK_SESSION_ID,
    group_id: group.id,
    present: [...body.present],
    phase: 'tiles',
    read_along_story_id: 'st_l1_001',
  }
  turnNumber = 1
  storyRound = newStoryRound(session, group.learners)
  events = []
  return clone(session)
}

export async function getStory(storyId) {
  await delay()
  const story = stories[storyId]
  if (!story) throw apiError(404, `story '${storyId}' not found`)
  // Estimated timings, same formula as backend/main.py until real audio exists.
  const words = []
  let t = 0
  for (const text of story.paragraphs.join(' ').split(/\s+/)) {
    const length = 150 + 80 * text.length
    words.push({ text, start_ms: t, end_ms: t + length })
    t += length + 150
  }
  return clone({
    title: story.title,
    paragraphs: story.paragraphs,
    words,
    audio_url: `/api/audio/${storyId}.wav`,
  })
}

export async function setPhase(sessionId, body) {
  await delay()
  requireSession(sessionId)
  if (!(body.phase in PHASE_MINUTES)) throw apiError(422, 'phase must be tiles, stories or summary')
  session.phase = body.phase
  const endsAt = new Date(Date.now() + PHASE_MINUTES[body.phase] * 60_000)
  return { phase: body.phase, ends_at: localIso(endsAt) }
}

// Turns rotate through `present` in group order (absent learners are skipped).
function currentTurn() {
  const childId = session.present[(turnNumber - 1) % session.present.length]
  return { ...items[(turnNumber - 1) % items.length], child_id: childId }
}

export async function getNextTurn(sessionId) {
  await delay()
  requireSession(sessionId)
  const { answer: _answer, ...turn } = currentTurn()
  return clone({
    ...turn,
    child_name: nameOf(turn.child_id),
    turn_number: turnNumber,
    item: { ...turn.item, prompt_audio: `/api/audio/${turn.item.id}.wav` },
    seconds: ITEM_SECONDS,
  })
}

export async function submitAnswer(sessionId, body) {
  await delay()
  requireSession(sessionId)
  const turn = currentTurn()
  if (body.item_id !== turn.item.id || body.child_id !== turn.child_id) {
    throw apiError(409, 'this is not the current turn; call /next first')
  }
  const name = nameOf(turn.child_id)
  const expected = turn.answer
  const correct =
    body.given.length === expected.length && body.given.every((tile, i) => tile === expected[i])
  events.push({ child_id: turn.child_id, item_id: turn.item.id, attempt: body.attempt, correct })

  if (correct) {
    const n = events.filter((e) => e.child_id === turn.child_id && e.correct).length - 1
    turnNumber += 1
    const lines = FEEDBACK_TEMPLATES.CORRECT.message_fil
    return {
      correct: true,
      mistake_type: null,
      feedback: { message_fil: lines[n % lines.length].replace('{name}', name), hint_fil: null },
      hint: null,
      next_action: 'next',
      answer: null,
    }
  }

  if (body.attempt <= HINT_LADDER.length) {
    const kind = HINT_LADDER[body.attempt - 1]
    let diff = expected.findIndex((tile, i) => i >= body.given.length || body.given[i] !== tile)
    if (diff === -1) diff = expected.length - 1
    return {
      correct: false,
      mistake_type: null,
      feedback: { message_fil: null, hint_fil: null },
      hint: {
        kind,
        audio: kind === 'replay_by_syllable' ? `/api/audio/${turn.item.id}_slow.wav` : null,
        highlight_slot: { highlight_slot: diff, first_tile: 0 }[kind] ?? null,
      },
      next_action: 'retry',
      answer: null,
    }
  }

  const show = FEEDBACK_TEMPLATES.SHOW_ANSWER
  return {
    correct: false,
    mistake_type: null,
    feedback: { message_fil: show.message_fil[0], hint_fil: show.hint_fil },
    hint: null,
    next_action: 'show_answer',
    answer: [...expected],
  }
}

// PROPOSAL, not in API_CONTRACT.md: one story question per turn, learners in turn order,
// questions from the read-along story. Kept apart from the mock session so it also runs next
// to a real backend session (src/api.js calls startStoryRound).
function newStoryRound(forSession, learners) {
  return {
    sessionId: forSession.id,
    present: [...forSession.present],
    names: Object.fromEntries(learners.map((l) => [l.id, l.name])),
    storyId: stories[forSession.read_along_story_id] ? forSession.read_along_story_id : 'st_l1_001',
    turn: 0,
  }
}

export function startStoryRound(forSession, learners) {
  storyRound = newStoryRound(forSession, learners)
}

function requireStoryRound(sessionId) {
  if (!storyRound || storyRound.sessionId !== sessionId) {
    throw apiError(404, `session '${sessionId}' not found`)
  }
}

function currentStoryQuestion() {
  const story = stories[storyRound.storyId]
  if (storyRound.turn >= story.questions.length) return null
  return {
    childId: storyRound.present[storyRound.turn % storyRound.present.length],
    question: story.questions[storyRound.turn],
  }
}

// Returns null when every question is done.
export async function getStoryTurn(sessionId) {
  await delay()
  requireStoryRound(sessionId)
  const current = currentStoryQuestion()
  if (!current) return null
  const { answer: _answer, ...question } = current.question
  return clone({
    child_id: current.childId,
    child_name: storyRound.names[current.childId],
    turn_number: storyRound.turn + 1,
    questions_total: stories[storyRound.storyId].questions.length,
    story_id: storyRound.storyId,
    question: { ...question, prompt_audio: `/api/audio/${question.id}.wav` },
  })
}

// PROPOSAL: body = { child_id, question_id, choice, attempt }. A second wrong answer
// reveals the answer and ends the question.
export async function submitStoryAnswer(sessionId, body) {
  await delay()
  requireStoryRound(sessionId)
  const current = currentStoryQuestion()
  if (!current || body.question_id !== current.question.id || body.child_id !== current.childId) {
    throw apiError(409, 'this is not the current question')
  }
  const name = storyRound.names[current.childId]
  if (body.choice === current.question.answer) {
    storyRound.turn += 1
    const lines = FEEDBACK_TEMPLATES.CORRECT.message_fil
    return {
      correct: true,
      feedback: { message_fil: lines[storyRound.turn % lines.length].replace('{name}', name), hint_fil: null },
      next_action: 'next',
      answer: null,
    }
  }
  if (body.attempt < 2) {
    return {
      correct: false,
      feedback: { message_fil: FEEDBACK_TEMPLATES.C_LITERAL.message_fil[0], hint_fil: null },
      next_action: 'retry',
      answer: null,
    }
  }
  storyRound.turn += 1
  return {
    correct: false,
    feedback: { message_fil: FEEDBACK_TEMPLATES.SHOW_ANSWER.message_fil[0], hint_fil: null },
    next_action: 'next',
    answer: current.question.answer,
  }
}

export async function getSummary(sessionId) {
  await delay(900)
  requireSession(sessionId)
  const learners = session.present.map((childId) => {
    const mine = events.filter((e) => e.child_id === childId)
    const itemsSeen = new Set(mine.map((e) => e.item_id))
    const firstTry = new Set(mine.filter((e) => e.attempt === 1 && e.correct).map((e) => e.item_id))
    return {
      child_id: childId,
      summary: `${nameOf(childId)}: ${firstTry.size} of ${itemsSeen.size} correct. Next: Vowel sounds with minimal pair vowels.`,
      next_focus_skill: 'sk_vowels',
      next_method: 'minimal_pair_vowels',
    }
  })
  return { learners, group_note: '' }
}

// Words, sentence and home line as in the API_CONTRACT.md example (weakest skill: sk_vowels).
const PRACTICE_SHEET = {
  words: [
    { text: 'aso', syllables: ['a', 'so'] },
    { text: 'ahas', syllables: ['a', 'has'] },
    { text: 'elepante', syllables: ['e', 'le', 'pan', 'te'] },
    { text: 'eroplano', syllables: ['e', 'ro', 'pla', 'no'] },
    { text: 'ibon', syllables: ['i', 'bon'] },
  ],
  sentence: 'Si Ana ay nasa bahay.',
  home_line_fil: 'Basahin nang malakas ang mga salitang ito kasama ang isang kasama sa bahay.',
}

export async function getPracticeSheet(childId) {
  await delay()
  const learner = group.learners.find((l) => l.id === childId)
  if (!learner) throw apiError(404, `child '${childId}' not found`)
  return clone({ name: learner.name, date: localIso(new Date()).slice(0, 10), ...PRACTICE_SHEET })
}

// Offline stand-in for GET /api/children/{id}/profile (the real profile comes from backend/adapt.py).
export async function getProfile(childId) {
  await delay()
  const learner = group.learners.find((l) => l.id === childId)
  if (!learner) throw apiError(404, `children '${childId}' not found`)
  const mine = events.filter((e) => e.child_id === childId && e.attempt === 1)
  const right = mine.filter((e) => e.correct).length
  return clone({
    child_id: childId,
    name: learner.name,
    profile: learner.profile,
    interests: [],
    diagnostic: null,
    story_level: 1,
    pace: null,
    current_skill: { id: 'sk_cvcv_1', name: 'CV-CV words', score: 0 },
    mastered: [],
    strengths: [],
    needs_work: [],
    methods: [],
    stars: right,
    streak: 0,
    sessions: mine.length ? [{ session_id: MOCK_SESSION_ID, date: '', correct: right, total: mine.length }] : [],
  })
}
