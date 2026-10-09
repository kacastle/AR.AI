// Single entry point for backend calls (backend/API_CONTRACT.md).
// VITE_USE_MOCK=true (default in .env) uses the offline mock in mocks/api.js.
// VITE_USE_MOCK=false calls the backend at VITE_API_BASE_URL (default http://localhost:8000).
// If the backend can't be reached before a session has started, the app switches to the mock
// for the rest of the visit. Once a real session exists, errors go to the screens instead,
// so real and mock data are never mixed.
import * as mock from './mocks/api.js'

export { SKILL_NAMES_FIL } from './mocks/api.js'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'
// Empty (the default): same origin, through Vite's /api proxy to the backend (vite.config.js).
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

const TIMEOUT_MS = 5000
const GROUP_KEY = 'rtph.group_id'
const groupKey = () => `${GROUP_KEY}.${GROUP_KEY_VERSION}`

// The tutor's group is created in the sign-up (names, pictures, interests); its id is kept in localStorage
// so later visits reuse it. A new learner field set means a new key, so old groups are not reused.
const GROUP_KEY_VERSION = 'v3'

let mode = USE_MOCK ? 'mock' : 'server' // 'mock' | 'server' | 'fallback'
let realSession = false
const listeners = new Set()

export const getApiMode = () => mode

export function subscribeApiMode(callback) {
  listeners.add(callback)
  return () => listeners.delete(callback)
}

function setMode(next) {
  mode = next
  listeners.forEach((callback) => callback())
}

export class ApiError extends Error {
  constructor(status, detail, unreachable = false) {
    super(detail)
    this.status = status
    this.detail = detail
    this.unreachable = unreachable
  }
}

async function request(method, path, body) {
  let response
  try {
    response = await fetch(API_BASE_URL + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch {
    throw new ApiError(0, `backend unreachable at ${API_BASE_URL || window.location.origin}/api (is uvicorn running on port 8000?)`, true)
  }
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      // Error body was not JSON.
    }
    throw new ApiError(response.status, detail)
  }
  return response.json()
}

async function call(server, offline) {
  if (mode !== 'server') return offline()
  try {
    return await server()
  } catch (error) {
    if (!error.unreachable || realSession) throw error
    console.warn(`${error.detail}; using offline demo data`)
    setMode('fallback')
    return offline()
  }
}

// Audio paths in the contract are relative to the backend.
const absolute = (path) => (path?.startsWith('/') ? API_BASE_URL + path : path)

export const login = (body) =>
  call(() => request('POST', '/api/tutor/login', body), () => mock.login(body))

// The saved group, or null when the tutor has not signed up the learners yet.
export const getSavedGroup = () =>
  call(
    async () => {
      const saved = localStorage.getItem(groupKey())
      if (!saved) return null
      try {
        return await request('GET', `/api/groups/${saved}`)
      } catch (error) {
        if (error.status !== 404) throw error
        localStorage.removeItem(groupKey())
        return null
      }
    },
    () => mock.getGroup(mock.MOCK_GROUP_ID),
  )

// body = { tutor_name, learners: [{ name, picture, profile, interests, diagnostic }] }
export const createGroup = (body) =>
  call(
    async () => {
      const group = await request('POST', '/api/groups', body)
      localStorage.setItem(groupKey(), group.id)
      return group
    },
    () => mock.createGroup(body),
  )

// Every saved learner on this laptop (returning learners keep their progress): GET /api/learners.
export const getLearners = () => call(() => request('GET', '/api/learners'), () => Promise.resolve([]))

export const forgetGroup = () => localStorage.removeItem(groupKey())

// The interest catalog for the sign-up: [{ id, label_fil, label_en, icon }].
export const getInterests = () => call(() => request('GET', '/api/interests'), () => mock.getInterests())

export const createSession = (body) =>
  call(
    async () => {
      const session = await request('POST', '/api/sessions', body)
      realSession = true
      return session
    },
    () => mock.createSession(body),
  )

export const getStory = (storyId) =>
  call(
    async () => {
      const story = await request('GET', `/api/stories/${storyId}`)
      return { ...story, audio_url: absolute(story.audio_url) }
    },
    () => mock.getStory(storyId),
  )

export const setPhase = (sessionId, body) =>
  call(() => request('POST', `/api/sessions/${sessionId}/phase`, body), () => mock.setPhase(sessionId, body))

export const getNextTurn = (sessionId) =>
  call(
    async () => {
      const turn = await request('GET', `/api/sessions/${sessionId}/next`)
      return { ...turn, item: { ...turn.item, prompt_audio: absolute(turn.item.prompt_audio) } }
    },
    () => mock.getNextTurn(sessionId),
  )

export const submitAnswer = (sessionId, body) =>
  call(
    async () => {
      const result = await request('POST', `/api/sessions/${sessionId}/answer`, body)
      return result.hint ? { ...result, hint: { ...result.hint, audio: absolute(result.hint.audio) } } : result
    },
    () => mock.submitAnswer(sessionId, body),
  )

export const getSummary = (sessionId) =>
  call(() => request('GET', `/api/sessions/${sessionId}/summary`), () => mock.getSummary(sessionId))

export const getPracticeSheet = (childId) =>
  call(() => request('GET', `/api/children/${childId}/sheet`), () => mock.getPracticeSheet(childId))

// Story phase: each learner reads their own story (story_id), then answers its questions.
// Returns null when every learner is done.
export const getStoryTurn = (sessionId) =>
  call(() => request('GET', `/api/sessions/${sessionId}/story_turn`), () => mock.getStoryTurn(sessionId))

// body = { child_id, question_id, choice, attempt }. The last first answer returns `quiz` with the next story level.
export const submitStoryAnswer = (sessionId, body) =>
  call(
    () => request('POST', `/api/sessions/${sessionId}/story_answer`, body),
    () => mock.submitStoryAnswer(sessionId, body),
  )

// Learner profile for the tutor and parents (skills, level, pace, interests, approaches that worked).
export const getProfile = (childId) =>
  call(() => request('GET', `/api/children/${childId}/profile`), () => mock.getProfile(childId))
