// Offline mock of the backend endpoints in backend/API_CONTRACT.md:
//   GET  /api/sessions/{id}/next    -> getNextTurn(sessionId)
//   POST /api/sessions/{id}/answer  -> submitAnswer(sessionId, body)
// Shapes, hint ladder and feedback lines mirror backend/main.py and content/rules.json.
// Items come from content/content.json. Learner names are fake. No network calls are made.

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
  seconds: 60,
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
}

const learners = {
  c_ana: 'Ana',
  c_ben: 'Ben',
  c_carlo: 'Carlo',
}

// Each turn: what /next returns plus the expected answer the server keeps to itself.
const turns = [
  { ...mockNextTurnPayload, answer: ['b', 'a', 't', 'a'] },
  {
    child_id: 'c_ben',
    task_type: 'dictation_syllables',
    item: { id: 'w_bahay', slots: 2, tiles: ['hay', 'lat', 'ba', 'ak'], syllables: ['ba', 'hay'] },
    support_level: 'guide',
    prefill: ['ba', ''],
    answer: ['ba', 'hay'],
  },
  {
    child_id: 'c_carlo',
    task_type: 'missing_letter',
    item: { id: 'w_aso', slots: 3, tiles: ['u', 'a', 'e', 'i'], syllables: ['a', 'so'] },
    support_level: 'alone',
    prefill: ['', 's', 'o'],
    answer: ['a', 's', 'o'],
  },
  {
    child_id: 'c_ana',
    task_type: 'dictation_letters',
    item: {
      id: 'w_saging',
      slots: 5,
      tiles: ['g', 'ng', 's', 'n', 'a', 'k', 'i', 'g'],
      syllables: ['sa', 'ging'],
    },
    support_level: 'show',
    prefill: ['s', 'a', 'g', 'i', 'ng'],
    answer: ['s', 'a', 'g', 'i', 'ng'],
  },
  {
    child_id: 'c_ben',
    task_type: 'sentence_builder',
    item: { id: 'sn_002', slots: 4, tiles: ['aso', 'Ben.', 'May', 'si'], syllables: [] },
    support_level: 'alone',
    prefill: ['', '', '', ''],
    answer: ['May', 'aso', 'si', 'Ben.'],
  },
]

const delay = (ms = 150) => new Promise((resolve) => setTimeout(resolve, ms))
const clone = (value) => JSON.parse(JSON.stringify(value))

let turnNumber = 1
let correctByChild = {}

function currentTurn() {
  return turns[(turnNumber - 1) % turns.length]
}

function apiError(status, detail) {
  const error = new Error(detail)
  error.status = status
  error.detail = detail
  return error
}

export async function getNextTurn(sessionId) {
  await delay()
  if (sessionId !== MOCK_SESSION_ID) throw apiError(404, `unknown session '${sessionId}'`)
  const { answer: _answer, ...turn } = currentTurn()
  return clone({
    ...turn,
    child_name: learners[turn.child_id],
    turn_number: turnNumber,
    item: { ...turn.item, prompt_audio: `/api/audio/${turn.item.id}.wav` },
    seconds: 60,
  })
}

export async function submitAnswer(sessionId, body) {
  await delay()
  if (sessionId !== MOCK_SESSION_ID) throw apiError(404, `unknown session '${sessionId}'`)
  const turn = currentTurn()
  if (body.item_id !== turn.item.id || body.child_id !== turn.child_id) {
    throw apiError(409, 'this is not the current turn; call /next first')
  }
  const name = learners[turn.child_id]
  const expected = turn.answer
  const correct =
    body.given.length === expected.length && body.given.every((tile, i) => tile === expected[i])

  if (correct) {
    const n = correctByChild[turn.child_id] ?? 0
    correctByChild[turn.child_id] = n + 1
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
    feedback: { message_fil: show.message_fil[0].replace('{name}', name), hint_fil: show.hint_fil },
    hint: null,
    next_action: 'show_answer',
    answer: [...expected],
  }
}

export function resetMockSession() {
  turnNumber = 1
  correctByChild = {}
}
