import { useCallback, useEffect, useRef, useState } from 'react'
import Tile from '../components/Tile.jsx'
import Slot from '../components/Slot.jsx'
import FeedbackBanner from '../components/FeedbackBanner.jsx'
import FeedbackOverlay from '../components/FeedbackOverlay.jsx'
import TurnSwitchScreen from './TurnSwitchScreen.jsx'
import { MOCK_SESSION_ID, getNextTurn, submitAnswer } from '../mocks/api.js'
import { t } from '../strings.js'
import './TileBoardScreen.css'

const SESSION_ID = MOCK_SESSION_ID
const SHAKE_MS = 450

function SpeakerIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor" />
      <path
        d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  )
}

function playAudio(url) {
  if (!url) return
  new Audio(url).play().catch(() => {})
}

// Turns the API's prefill into the starting board.
// "show" displays the answer as a model and the learner rebuilds it; other prefill
// entries are fixed tiles the learner cannot remove.
function buildBoard(turn) {
  const { task_type, support_level, prefill, item } = turn
  const fixed = (text) => ({ text, fixed: true })

  if (support_level === 'show') {
    if (task_type === 'missing_letter') {
      // The gap is the box whose letter is one of the candidate tiles.
      const gap = Math.max(0, prefill.findIndex((p) => item.tiles.includes(p)))
      return { model: prefill, base: prefill.map((p, i) => (i === gap ? null : fixed(p))), consumed: [] }
    }
    return { model: prefill, base: prefill.map(() => null), consumed: [] }
  }

  const base = prefill.map((p) => (p ? fixed(p) : null))
  const consumed = []
  if (task_type !== 'missing_letter') {
    for (const p of prefill.filter(Boolean)) {
      const index = item.tiles.findIndex((tile, i) => tile === p && !consumed.includes(i))
      if (index !== -1) consumed.push(index)
    }
  }
  return { model: null, base, consumed }
}

export default function TileBoardScreen() {
  const [turn, setTurn] = useState(null)
  const [board, setBoard] = useState(null)
  const [slots, setSlots] = useState([])
  const [model, setModel] = useState(null)
  const [result, setResult] = useState(null)
  const [overlay, setOverlay] = useState(null)
  const [shake, setShake] = useState(false)
  const [attempt, setAttempt] = useState(1)
  const [hintsUsed, setHintsUsed] = useState(0)
  const [highlight, setHighlight] = useState(null)
  const [activeChild, setActiveChild] = useState(null)
  const [status, setStatus] = useState('loading')
  const [busy, setBusy] = useState(false)
  const itemStart = useRef(0)
  const shakeTimer = useRef(null)

  const applyTurn = useCallback((next) => {
    const nextBoard = buildBoard(next)
    clearTimeout(shakeTimer.current)
    setTurn(next)
    setBoard(nextBoard)
    setSlots(nextBoard.base)
    setModel(nextBoard.model)
    setResult(null)
    setOverlay(null)
    setShake(false)
    setAttempt(1)
    setHintsUsed(0)
    setHighlight(null)
    setStatus('ready')
    itemStart.current = Date.now()
  }, [])

  useEffect(() => {
    let cancelled = false
    getNextTurn(SESSION_ID)
      .then((next) => !cancelled && applyTurn(next))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
      clearTimeout(shakeTimer.current)
    }
  }, [applyTurn])

  const loadTurn = () => {
    setStatus('loading')
    getNextTurn(SESSION_ID)
      .then(applyTurn)
      .catch(() => setStatus('error'))
  }

  if (status === 'loading') {
    return <main className="board board--center">{t.loading}</main>
  }

  if (status === 'error') {
    return (
      <main className="board board--center">
        <p>{t.loadError}</p>
        <button type="button" className="action action--primary" onClick={loadTurn}>
          {t.retry}
        </button>
      </main>
    )
  }

  if (turn.child_id !== activeChild) {
    const start = () => {
      setActiveChild(turn.child_id)
      itemStart.current = Date.now()
      playAudio(turn.item.prompt_audio)
    }
    return <TurnSwitchScreen name={turn.child_name} onStart={start} />
  }

  const keepCase = turn.task_type === 'sentence_builder'
  const locked = result?.next_action === 'next' || busy || shake || Boolean(overlay)
  const usedTiles = new Set([
    ...board.consumed,
    ...slots.filter((s) => s && !s.fixed).map((s) => s.tileIndex),
  ])
  const allFilled = slots.every(Boolean)
  const hasPlaced = slots.some((s) => s && !s.fixed)

  const edit = (update) => {
    setResult(null)
    setHighlight(null)
    setSlots(update)
  }

  const placeTile = (tileIndex) => {
    const empty = slots.indexOf(null)
    if (locked || empty === -1) return
    const placed = { text: turn.item.tiles[tileIndex], fixed: false, tileIndex }
    edit((prev) => prev.map((s, i) => (i === empty ? placed : s)))
  }

  const removeTile = (index) => {
    if (locked || slots[index]?.fixed) return
    edit((prev) => prev.map((s, i) => (i === index ? null : s)))
  }

  const clearSlots = () => edit(board.base)

  const checkAnswer = async () => {
    setBusy(true)
    try {
      const response = await submitAnswer(SESSION_ID, {
        child_id: turn.child_id,
        item_id: turn.item.id,
        given: slots.map((s) => s.text),
        hints_used: hintsUsed,
        attempt,
        time_ms: Date.now() - itemStart.current,
      })
      if (response.correct) {
        setResult(response)
        return
      }
      setAttempt((a) => a + 1)
      if (response.hint) {
        setHintsUsed((n) => n + 1)
        setHighlight(response.hint.highlight_slot)
        playAudio(response.hint.audio)
      }
      setShake(true)
      clearTimeout(shakeTimer.current)
      shakeTimer.current = setTimeout(() => {
        setShake(false)
        setOverlay(response)
      }, SHAKE_MS)
    } catch {
      setResult({ error: true })
    } finally {
      setBusy(false)
    }
  }

  const showAnswer = () => {
    setModel(overlay.answer)
    setSlots(board.base)
    setHighlight(null)
    setOverlay(null)
  }

  const feedback =
    result &&
    (result.error ? (
      <FeedbackBanner tone="incorrect" message={t.loadError} />
    ) : (
      <FeedbackBanner
        tone="correct"
        message={result.feedback.message_fil}
        hint={result.feedback.hint_fil}
      />
    ))

  return (
    <main className="board">
      <header className="board__header">
        <span className="board__progress">{t.turnLabel(turn.turn_number)}</span>
        <span className="board__learner">{t.learnerTurn(turn.child_name)}</span>
      </header>

      <p className="board__instruction">{t.instructions[turn.task_type]}</p>

      <button
        type="button"
        className="action board__listen"
        onClick={() => playAudio(turn.item.prompt_audio)}
      >
        <SpeakerIcon />
        {t.listen}
      </button>

      {model && (
        <section className="board__model" aria-label={t.modelLabel}>
          <span className="board__model-label">{t.modelLabel}</span>
          <div className="board__model-tiles">
            {model.map((text, i) => (
              <span key={i} className={`tile tile--model${keepCase ? ' tile--keep-case' : ''}`}>
                {keepCase ? text : text.toLowerCase()}
              </span>
            ))}
          </div>
        </section>
      )}

      <section
        className={`board__slots${shake ? ' board__slots--shake' : ''}`}
        aria-label={t.slotsLabel}
      >
        {slots.map((slot, i) => (
          <Slot
            key={i}
            index={i}
            slot={slot}
            onRemove={removeTile}
            locked={locked}
            highlighted={highlight === i}
            keepCase={keepCase}
          />
        ))}
      </section>

      <div className="board__feedback">{feedback}</div>

      <section className="board__tray" aria-label={t.trayLabel}>
        {turn.item.tiles.map((text, i) =>
          usedTiles.has(i) ? (
            <div key={i} className="board__tray-gap" aria-hidden="true" />
          ) : (
            <Tile
              key={i}
              text={text}
              onClick={() => placeTile(i)}
              ariaLabel={t.availableTile(text)}
              disabled={locked || allFilled}
              keepCase={keepCase}
            />
          ),
        )}
      </section>

      <footer className="board__actions">
        {result?.next_action === 'next' ? (
          <button type="button" className="action action--primary action--glow" onClick={loadTurn}>
            {t.next}
          </button>
        ) : (
          <>
            <button
              type="button"
              className="action"
              onClick={clearSlots}
              disabled={!hasPlaced || locked}
            >
              {t.clear}
            </button>
            <button
              type="button"
              className="action action--primary"
              onClick={checkAnswer}
              disabled={!allFilled || locked}
            >
              {t.check}
            </button>
          </>
        )}
      </footer>

      {overlay && (
        <FeedbackOverlay
          response={overlay}
          name={turn.child_name}
          onRetry={() => setOverlay(null)}
          onShowAnswer={showAnswer}
          onListen={playAudio}
        />
      )}
    </main>
  )
}
