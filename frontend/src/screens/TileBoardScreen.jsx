import { useCallback, useEffect, useRef, useState } from 'react'
import FeedbackBanner from '../components/FeedbackBanner.jsx'
import FeedbackOverlay from '../components/FeedbackOverlay.jsx'
import TurnSwitchScreen from './TurnSwitchScreen.jsx'
import LessonScreen from './LessonScreen.jsx'
import ProgressScreen from './ProgressScreen.jsx'
import ReadAlongScreen from './ReadAlongScreen.jsx'
import Confetti from '../components/Confetti.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import LearnerPicture from '../components/LearnerPicture.jsx'
import { playChime, playPop } from '../sfx.js'
import { useAudio } from '../hooks/useAudio.js'
import SpeakerIcon from '../components/SpeakerIcon.jsx'
import { getNextTurn, submitAnswer } from '../api.js'
import { t } from '../strings.js'

const SHAKE_MS = 450

const SLATE = '#1E3A5F'
const GREEN = '#2FA84F'
const ORANGE = '#F28C28'

// Built-in icons instead of emoji: emoji show as empty boxes on devices without an emoji font.
const icon = (d) => (
  <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" style={{ flexShrink: 0 }}>
    <path d={d} fill="currentColor" />
  </svg>
)
const NAV = [
  { id: 'practice', icon: icon('M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z') },
  { id: 'stories', icon: icon('M4 5c3-1.5 5.5-1.5 8 .5V20c-2.5-2-5-2-8-.5zM20 5c-3-1.5-5.5-1.5-8 .5V20c2.5-2 5-2 8-.5z') },
  { id: 'progress', icon: icon('M4 20V10h3v10zM10.5 20V4h3v16zM17 20v-7h3v7z') },
]

const S = {
  layout: {
    display: 'grid',
    gridTemplateColumns: 'minmax(220px, 260px) 1fr',
    gap: 20,
    maxWidth: 1180,
    margin: '0 auto',
    padding: '20px 16px 32px',
    boxSizing: 'border-box',
    alignItems: 'start',
  },
  sidebar: {
    background: '#fff',
    border: '1px solid #E5E7EB',
    borderRadius: 20,
    padding: 18,
    display: 'flex',
    flexDirection: 'column',
    gap: 18,
    boxShadow: '0 4px 14px rgba(0, 0, 0, 0.04)',
  },
  profile: { display: 'flex', gap: 12, alignItems: 'center' },
  name: { margin: 0, fontSize: 22, fontWeight: 800, color: SLATE },
  role: { margin: '2px 0 6px', fontSize: 15, color: '#6B7280' },
  starBadge: {
    display: 'inline-block',
    whiteSpace: 'nowrap',
    padding: '3px 10px',
    borderRadius: 999,
    background: '#FFE27A',
    color: '#5C4400',
    fontWeight: 800,
    fontSize: 14,
  },
  streak: {
    whiteSpace: 'nowrap',
    padding: '3px 8px',
    borderRadius: 999,
    background: '#FFE9C7',
    fontWeight: 700,
    fontSize: 14,
  },
  nav: { display: 'flex', flexDirection: 'column', gap: 6 },
  navButton: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    width: '100%',
    padding: '12px 14px',
    border: 'none',
    borderRadius: 12,
    background: 'transparent',
    color: '#374151',
    fontFamily: 'inherit',
    fontSize: 17,
    fontWeight: 700,
    textAlign: 'left',
    cursor: 'pointer',
  },
  navActive: { background: '#E7F6EC', color: '#1F7A37' },
  tip: {
    margin: 0,
    padding: 14,
    borderRadius: 14,
    background: '#E8F1FB',
    border: '1px solid #C9DDF3',
    color: '#1E4E7A',
    fontSize: 15,
    lineHeight: 1.45,
  },
  board: {
    background: '#fff',
    border: '1px solid #E5E7EB',
    borderRadius: 24,
    padding: '20px 24px 28px',
    minHeight: 520,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 20,
    boxShadow: '0 4px 14px rgba(0, 0, 0, 0.04)',
    minWidth: 0,
  },
  boardHeader: { width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  question: { fontSize: 22, fontWeight: 800, color: SLATE },
  modeBadge: {
    padding: '4px 12px',
    borderRadius: 999,
    background: '#F1F5F9',
    color: '#475569',
    fontSize: 14,
    fontWeight: 700,
  },
  tutorNote: { margin: 0, fontSize: 14, color: '#6B7280', textAlign: 'center' },
  instruction: {
    margin: '8px 0 0',
    fontSize: 'clamp(22px, 3vw, 30px)',
    fontWeight: 800,
    color: SLATE,
    textAlign: 'center',
  },
  listen: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: '12px 28px',
    border: 'none',
    borderRadius: 999,
    background: '#FFD84D',
    color: '#4A3800',
    fontFamily: 'inherit',
    fontSize: 20,
    fontWeight: 800,
    cursor: 'pointer',
    boxShadow: '0 4px 0 #E0B400',
  },
  row: { display: 'flex', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', gap: 12 },
  modelLabel: { fontSize: 16, color: '#6B7280', fontWeight: 700 },
  square: {
    minWidth: 72,
    height: 72,
    padding: '0 12px',
    boxSizing: 'border-box',
    borderRadius: 14,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'inherit',
    fontSize: 32,
    fontWeight: 800,
  },
  gap: { border: `3px dashed ${ORANGE}`, background: '#FFF7EC' },
  filled: { border: 'none', background: '#E5E7EB', color: '#1F2937' },
  placed: { border: 'none', background: '#D1D5DB', color: '#111827', cursor: 'pointer' },
  modelTile: { minWidth: 56, height: 56, fontSize: 26, background: '#F3F4F6', color: '#374151' },
  highlight: { outline: '4px solid #3A9BD9', outlineOffset: 3 },
  choice: {
    border: 'none',
    borderBottom: '6px solid #D9822B',
    background: 'linear-gradient(180deg, #FFD36B, #FFB23F)',
    color: '#4A2C00',
    cursor: 'pointer',
  },
  feedback: { minHeight: 48, width: '100%', display: 'flex', justifyContent: 'center' },
  actions: { display: 'flex', gap: 16, justifyContent: 'center', marginTop: 'auto', flexWrap: 'wrap' },
  btn: {
    minWidth: 150,
    padding: '14px 28px',
    border: 'none',
    borderRadius: 999,
    fontFamily: 'inherit',
    fontSize: 20,
    fontWeight: 800,
    cursor: 'pointer',
  },
  secondary: { background: '#E5E7EB', color: '#374151', boxShadow: '0 4px 0 #C4C8CE' },
  primary: { background: GREEN, color: '#fff', boxShadow: '0 4px 0 #1F7A37' },
  center: {
    minHeight: 300,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  masteredBackdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15, 23, 42, 0.45)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 50,
  },
  masteredCard: { background: '#fff', borderRadius: 24, padding: 32, textAlign: 'center', maxWidth: 420, margin: 16 },
  masteredName: { fontSize: 26, fontWeight: 800, color: SLATE, margin: '8px 0' },
}

const CSS = `
.tb-avatar { width: 64px; height: 64px; flex-shrink: 0; }
.tb-choice { transition: transform 160ms ease, box-shadow 160ms ease; }
.tb-choice:hover:not(:disabled) { transform: translateY(-4px); box-shadow: 0 8px 14px rgba(217, 130, 43, 0.35); }
.tb-choice:active:not(:disabled) { transform: translateY(2px); border-bottom-width: 2px !important; }
.tb-choice:disabled, .tb-btn:disabled { opacity: 0.45; cursor: default; }
.tb-btn, .tb-listen, .tb-nav { transition: transform 160ms ease, background 160ms ease; }
.tb-btn:hover:not(:disabled), .tb-listen:hover { transform: translateY(-2px); }
.tb-nav:hover:not([aria-current]) { background: #F3F4F6 !important; }
.tb-layout button:focus-visible { outline: 4px solid #3A9BD9; outline-offset: 3px; }
.tb-listen--speaking { animation: tb-pulse 1s ease-in-out infinite; }
@keyframes tb-pulse { 50% { transform: scale(1.06); } }
.tb-shake > * { animation: tb-shake 420ms ease-in-out; }
@keyframes tb-shake { 20%, 60% { transform: translateX(-8px) } 40%, 80% { transform: translateX(8px) } }
@media (max-width: 760px) { .tb-layout { grid-template-columns: 1fr !important; } }
@media (prefers-reduced-motion: reduce) { .tb-shake > *, .tb-listen--speaking { animation: none; } }
`

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

// The practice dashboard: the learner's card and menu on the left, the tile board on the right.
// The menu opens the learner's story and progress inside the board; the turn stays as it was.
export default function TileBoardScreen({ sessionId, session, learners, isPhaseOver, onDone }) {
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
  const [view, setView] = useState('practice') // practice, stories, progress
  const itemStart = useRef(0)
  const shakeTimer = useRef(null)
  const speaker = useAudio()
  const [stars, setStars] = useState({})
  const [burst, setBurst] = useState(0)
  const [lessonSeen, setLessonSeen] = useState(null) // turn_number whose lesson was shown
  const [mastered, setMastered] = useState(null) // skill name to celebrate

  const applyTurn = useCallback((next) => {
    const nextBoard = buildBoard(next)
    clearTimeout(shakeTimer.current)
    setTurn(next)
    // The server counts stars across sessions; the offline mock does not send them.
    if (typeof next.stars === 'number') setStars((s) => ({ ...s, [next.child_id]: next.stars }))
    setBoard(nextBoard)
    setSlots(nextBoard.base)
    setModel(nextBoard.model)
    setResult(null)
    setOverlay(null)
    setShake(false)
    setAttempt(1)
    setHintsUsed(0)
    setHighlight(null)
    setView('practice')
    setStatus('ready')
    itemStart.current = Date.now()
  }, [])

  useEffect(() => {
    let cancelled = false
    getNextTurn(sessionId)
      .then((next) => !cancelled && applyTurn(next))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
      clearTimeout(shakeTimer.current)
    }
  }, [applyTurn, sessionId])

  const loadTurn = () => {
    setStatus('loading')
    getNextTurn(sessionId)
      .then(applyTurn)
      .catch(() => setStatus('error'))
  }

  if (status === 'loading') {
    return <LoadingOverlay />
  }

  if (status === 'error') {
    return (
      <main style={S.center}>
        <p style={{ fontSize: 24 }}>{t.loadError}</p>
        <button type="button" style={{ ...S.btn, ...S.primary }} onClick={loadTurn}>
          {t.retry}
        </button>
      </main>
    )
  }

  const needsLesson = Boolean(turn.lesson) && lessonSeen !== turn.turn_number
  const picture = learners.find((l) => l.id === turn.child_id)?.picture ?? 'cat'

  if (turn.child_id !== activeChild) {
    const start = () => {
      setActiveChild(turn.child_id)
      itemStart.current = Date.now()
      if (!needsLesson) speaker.play(turn.item.prompt_audio)
    }
    return <TurnSwitchScreen name={turn.child_name} picture={picture} onStart={start} />
  }

  // Teach first: a new skill, or the same skill another way when the learner is stuck.
  if (needsLesson) {
    const practise = () => {
      setLessonSeen(turn.turn_number)
      itemStart.current = Date.now()
      speaker.play(turn.item.prompt_audio)
    }
    return <LessonScreen key={turn.turn_number} lesson={turn.lesson} childName={turn.child_name} onDone={practise} />
  }

  const keepCase = turn.task_type === 'sentence_builder'
  const show = (text) => (keepCase ? text : text.toLowerCase())
  const locked = result?.next_action === 'next' || busy || shake || Boolean(overlay)
  const usedTiles = new Set([
    ...board.consumed,
    ...slots.filter((s) => s && !s.fixed).map((s) => s.tileIndex),
  ])
  const allFilled = slots.every(Boolean)
  const hasPlaced = slots.some((s) => s && !s.fixed)
  const starCount = stars[turn.child_id] ?? 0
  const storyId = session?.story_ids?.[turn.child_id] ?? session?.read_along_story_id

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
    playPop()
  }

  const removeTile = (index) => {
    if (locked || slots[index]?.fixed) return
    edit((prev) => prev.map((s, i) => (i === index ? null : s)))
  }

  const clearSlots = () => edit(board.base)

  const checkAnswer = async () => {
    setBusy(true)
    try {
      const response = await submitAnswer(sessionId, {
        child_id: turn.child_id,
        item_id: turn.item.id,
        given: slots.map((s) => s.text),
        hints_used: hintsUsed,
        attempt,
        time_ms: Date.now() - itemStart.current,
      })
      if (response.correct) {
        setResult(response)
        setStars((s) => ({
          ...s,
          [turn.child_id]: typeof response.stars === 'number' ? response.stars : (s[turn.child_id] ?? 0) + 1,
        }))
        setBurst((b) => b + 1)
        playChime()
        if (response.mastered_skill) setMastered(response.mastered_skill)
        return
      }
      if (response.next_action === 'next') {
        // Wrong, but the item ends (a diagnostic item has one try; a wrong rebuild ends the item).
        setResult(response)
        return
      }
      setAttempt((a) => a + 1)
      if (response.hint) {
        setHintsUsed((n) => n + 1)
        setHighlight(response.hint.highlight_slot)
        speaker.play(response.hint.audio)
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
        tone={result.correct ? 'correct' : 'incorrect'}
        message={result.feedback.message_fil ?? t.tryAgain(turn.child_name)}
        hint={result.feedback.hint_fil}
      />
    ))

  const practice = (
    <>
      <header style={S.boardHeader}>
        <span style={S.question}>{t.turnLabel(turn.turn_number)}</span>
        <span style={S.modeBadge}>{t.dashboard.mode[turn.mode] ?? t.dashboard.mode.practice}</span>
      </header>

      {turn.mode === 'reteach' && turn.method_note && (
        <p style={S.tutorNote}>{t.tutorNotes.reteach(turn.method_note)}</p>
      )}

      <p style={S.instruction}>{t.instructions[turn.task_type]}</p>

      <button
        type="button"
        className={`tb-listen${speaker.speaking ? ' tb-listen--speaking' : ''}`}
        style={S.listen}
        onClick={() => speaker.play(turn.item.prompt_audio)}
      >
        <SpeakerIcon />
        {t.listen}
      </button>

      {model && (
        <section style={S.row} aria-label={t.modelLabel}>
          <span style={S.modelLabel}>{t.modelLabel}</span>
          {model.map((text, i) => (
            <span key={i} style={{ ...S.square, ...S.modelTile }}>
              {show(text)}
            </span>
          ))}
        </section>
      )}

      <section className={shake ? 'tb-shake' : undefined} style={S.row} aria-label={t.slotsLabel}>
        {slots.map((slot, i) => {
          const ring = highlight === i ? S.highlight : null
          if (!slot) {
            return (
              <div key={i} role="img" aria-label={t.emptySlot(i + 1)} style={{ ...S.square, ...S.gap, ...ring }} />
            )
          }
          return (
            <button
              key={i}
              type="button"
              onClick={() => removeTile(i)}
              disabled={locked || slot.fixed}
              aria-label={slot.fixed ? t.fixedTile(slot.text, i + 1) : t.placedTile(slot.text, i + 1)}
              style={{ ...S.square, ...(slot.fixed ? S.filled : S.placed), ...ring }}
            >
              {show(slot.text)}
            </button>
          )
        })}
      </section>

      <div style={S.feedback}>{feedback}</div>

      <section style={S.row} aria-label={t.trayLabel}>
        {turn.item.tiles.map((text, i) =>
          usedTiles.has(i) ? (
            <div key={i} style={{ ...S.square, visibility: 'hidden' }} aria-hidden="true" />
          ) : (
            <button
              key={i}
              type="button"
              className="tb-choice"
              onClick={() => placeTile(i)}
              aria-label={t.availableTile(text)}
              disabled={locked || allFilled}
              style={{ ...S.square, ...S.choice }}
            >
              {show(text)}
            </button>
          ),
        )}
      </section>

      <footer style={S.actions}>
        {result?.next_action === 'next' ? (
          <button
            type="button"
            className="tb-btn"
            style={{ ...S.btn, ...S.primary }}
            onClick={() => (isPhaseOver() ? onDone() : loadTurn())}
          >
            {t.next}
          </button>
        ) : (
          <>
            <button
              type="button"
              className="tb-btn"
              style={{ ...S.btn, ...S.secondary }}
              onClick={clearSlots}
              disabled={!hasPlaced || locked}
            >
              {t.clear}
            </button>
            <button
              type="button"
              className="tb-btn"
              style={{ ...S.btn, ...S.primary }}
              onClick={checkAnswer}
              disabled={!allFilled || locked}
            >
              {t.check} ✓
            </button>
          </>
        )}
      </footer>
    </>
  )

  return (
    <main className="tb-layout slide-in" style={S.layout}>
      <style>{CSS}</style>

      <aside style={S.sidebar}>
        <div style={S.profile}>
          <LearnerPicture picture={picture} label={t.turnSwitch.avatar(turn.child_name)} className="tb-avatar" />
          <div>
            <p style={S.name}>{turn.child_name}</p>
            <p style={S.role}>{t.dashboard.role}</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              <span style={S.starBadge}>★ {t.dashboard.stars(starCount)}</span>
              {turn.streak >= 2 && (
                <span style={S.streak} aria-label={t.streak(turn.streak)}>
                  🔥 {turn.streak}
                </span>
              )}
            </div>
          </div>
        </div>

        <nav aria-label={t.dashboard.navLabel} style={S.nav}>
          {NAV.map((item) => {
            const active = view === item.id
            return (
              <button
                key={item.id}
                type="button"
                className="tb-nav"
                aria-current={active ? 'page' : undefined}
                onClick={() => setView(item.id)}
                style={{ ...S.navButton, ...(active ? S.navActive : null) }}
              >
                {item.icon}
                {t.dashboard.nav[item.id]}
              </button>
            )
          })}
        </nav>

        <p style={S.tip}>💡 {t.dashboard.tip}</p>
      </aside>

      <section style={S.board}>
        {view === 'practice' && practice}
        {view === 'progress' && (
          <ProgressScreen
            childId={turn.child_id}
            picture={picture}
            onBack={() => setView('practice')}
            backLabel={t.profile.backToPractice}
          />
        )}
        {view === 'stories' &&
          (storyId ? (
            <ReadAlongScreen storyId={storyId} onDone={() => setView('practice')} />
          ) : (
            <p>{t.dashboard.noStory}</p>
          ))}
      </section>

      {overlay && (
        <FeedbackOverlay
          response={overlay}
          name={turn.child_name}
          onRetry={() => setOverlay(null)}
          onShowAnswer={showAnswer}
          onListen={speaker.play}
          speaking={speaker.speaking}
        />
      )}
      {burst > 0 && <Confetti key={burst} />}
      {mastered && (
        <div style={S.masteredBackdrop} role="dialog" aria-live="polite">
          <div className="pop-in" style={S.masteredCard}>
            <span style={{ fontSize: 64 }} aria-hidden="true">
              🏆
            </span>
            <p style={S.masteredName}>{mastered}</p>
            <p>{result?.feedback?.message_fil}</p>
            <button
              type="button"
              className="tb-btn"
              style={{ ...S.btn, ...S.primary }}
              onClick={() => setMastered(null)}
            >
              {t.next}
            </button>
          </div>
          <Confetti count={80} />
        </div>
      )}
    </main>
  )
}
