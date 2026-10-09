// Offline mock of the Reading Tutor PH backend. No network calls are made.
// `picture` is a key into the locally bundled SVGs in src/assets/pictures.

export const mockNextTurnPayload = {
  turn_id: 'turn-001',
  activity: 'tile_board',
  target_word: 'bata',
  picture: 'bata',
  slot_count: 2,
  tiles: [
    { id: 't1', text: 'ba' },
    { id: 't2', text: 'ka' },
    { id: 't3', text: 'ta' },
    { id: 't4', text: 'la' },
  ],
  progress: { current: 1, total: 3 },
}

export const mockAnswerPayload = {
  request: {
    turn_id: 'turn-001',
    placed_tile_ids: ['t1', 't3'],
    answer: 'bata',
  },
  response: {
    turn_id: 'turn-001',
    is_correct: true,
    correct_answer: 'bata',
    stars_earned: 1,
    has_next_turn: true,
  },
}

const turns = [
  mockNextTurnPayload,
  {
    turn_id: 'turn-002',
    activity: 'tile_board',
    target_word: 'aso',
    picture: 'aso',
    slot_count: 3,
    tiles: [
      { id: 't1', text: 's' },
      { id: 't2', text: 'a' },
      { id: 't3', text: 'm' },
      { id: 't4', text: 'o' },
      { id: 't5', text: 'i' },
    ],
    progress: { current: 2, total: 3 },
  },
  {
    turn_id: 'turn-003',
    activity: 'tile_board',
    target_word: 'bahay',
    picture: 'bahay',
    slot_count: 2,
    tiles: [
      { id: 't1', text: 'hay' },
      { id: 't2', text: 'ba' },
      { id: 't3', text: 'bi' },
      { id: 't4', text: 'lay' },
    ],
    progress: { current: 3, total: 3 },
  },
]

const delay = (ms = 150) => new Promise((resolve) => setTimeout(resolve, ms))
const clone = (value) => JSON.parse(JSON.stringify(value))

// Pass the previous turn_id (or nothing) to get the following turn.
export async function getNextTurn(afterTurnId = null) {
  await delay()
  const index = afterTurnId ? turns.findIndex((t) => t.turn_id === afterTurnId) + 1 : 0
  return clone(turns[index % turns.length])
}

export async function submitAnswer({ turn_id, placed_tile_ids, answer }) {
  await delay()
  const turn = turns.find((t) => t.turn_id === turn_id)
  if (!turn) throw new Error(`Unknown turn: ${turn_id}`)
  const normalized = answer.toLowerCase()
  const isCorrect = normalized === turn.target_word
  return {
    turn_id,
    placed_tile_ids,
    is_correct: isCorrect,
    correct_answer: turn.target_word,
    stars_earned: isCorrect ? 1 : 0,
    has_next_turn: turn.progress.current < turn.progress.total,
  }
}
