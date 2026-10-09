// Testbench stand-in for frontend/src/mocks/api.js: the same exports, but every call goes to the real
// backend through the Vite proxy (/api -> uvicorn). frontend/ is not changed; scripts/testbench/vite.config.mjs
// points the frontend's "mocks/api.js" import here. Learner names are fake.
//
// A session is created on first use and kept for the browser tab. Open the page with ?new to start over.

export const MOCK_SESSION_ID = 'testbench'

const KEY = 'testbench_session_id'
// Interests let the background model write personal stories (they appear in GET /api/approvals).
const LEARNERS = [
  { name: 'Ana', picture: 'cat', profile: 'low_emergent', interests: ['int_food', 'int_toys'] },
  { name: 'Ben', picture: 'dog', profile: 'high_emergent', interests: ['int_vehicles', 'int_basketball'] },
  { name: 'Carlo', picture: 'bird', profile: 'low_emergent', interests: ['int_drawing', 'int_music'] },
]

async function call(method, path, body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.detail || response.statusText)
    error.status = response.status
    error.detail = data.detail
    console.error(`[testbench] ${method} /api${path} -> ${response.status}`, data)
    throw error
  }
  return data
}

function stored() {
  try {
    if (new URLSearchParams(window.location.search).has('new')) return null
    return window.sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

async function createSession() {
  const group = await call('POST', '/groups', { tutor_name: 'Testbench', learners: LEARNERS })
  const session = await call('POST', '/sessions', {
    group_id: group.id,
    present: group.learners.map((l) => l.id),
  })
  try {
    window.sessionStorage.setItem(KEY, session.id)
  } catch {
    // Storage blocked: the session lasts until the page reloads.
  }
  console.info(`[testbench] new session ${session.id} (group ${group.id})`)
  return session.id
}

let sessionPromise = null

function realSessionId() {
  sessionPromise ??= (async () => {
    const id = stored()
    if (id) {
      try {
        await call('GET', `/sessions/${id}/next`)
        return id
      } catch {
        // The database was reset: start a new session.
      }
    }
    return createSession()
  })().catch((error) => {
    sessionPromise = null // let the screen's retry button try again
    throw error
  })
  return sessionPromise
}

export async function getNextTurn(_sessionId) {
  return call('GET', `/sessions/${await realSessionId()}/next`)
}

export async function submitAnswer(_sessionId, body) {
  return call('POST', `/sessions/${await realSessionId()}/answer`, body)
}

export function resetMockSession() {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    // nothing stored
  }
  sessionPromise = null
}
