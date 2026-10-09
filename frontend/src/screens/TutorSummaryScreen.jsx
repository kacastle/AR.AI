import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import Confetti from '../components/Confetti.jsx'
import LearnerPicture from '../components/LearnerPicture.jsx'
import { SKILL_NAMES_FIL, getPracticeSheet, getSummary } from '../api.js'
import { t } from '../strings.js'
import './TutorSummaryScreen.css'

function PrinterIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h10v5H7z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M5 8h14a2 2 0 0 1 2 2v6h-4v4H7v-4H3v-6a2 2 0 0 1 2-2z" fill="currentColor" />
      <path d="M8 14h8v5H8z" fill="#fff" />
    </svg>
  )
}

function PracticeSheet({ sheet }) {
  return (
    <article className="sheet">
      <header className="sheet__header">
        <h1 className="sheet__title">{t.sheet.title}</h1>
        <div className="sheet__meta">
          <span>
            {t.sheet.name} <strong>{sheet.name}</strong>
          </span>
          <span>
            {t.sheet.date} {sheet.date}
          </span>
        </div>
      </header>
      <h2 className="sheet__heading">{t.sheet.words}</h2>
      <ol className="sheet__words">
        {sheet.words.map((word) => (
          <li key={word.text} className="sheet__word">
            <span className="sheet__syllables">{word.syllables.join(' - ')}</span>
            <span className="sheet__whole">{word.text}</span>
            <span className="sheet__line" />
          </li>
        ))}
      </ol>
      <h2 className="sheet__heading">{t.sheet.sentence}</h2>
      <p className="sheet__sentence">{sheet.sentence}</p>
      <div className="sheet__line sheet__line--long" />
      <div className="sheet__line sheet__line--long" />
      <footer className="sheet__note">
        <strong>{t.sheet.parentNote}</strong> {sheet.home_line_fil}
      </footer>
    </article>
  )
}

export default function TutorSummaryScreen({ sessionId, learners, onRestart }) {
  const [summary, setSummary] = useState(null)
  const [sheets, setSheets] = useState(null)
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    getSummary(sessionId)
      .then((s) => !cancelled && setSummary(s))
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [sessionId])

  if (error) return <main className="screen screen--center">{t.loadError}</main>
  if (!summary) return <main className="screen screen--center">{t.loading}</main>

  const byId = Object.fromEntries(learners.map((l) => [l.id, l]))

  // One sheet per present learner (GET /api/children/{id}/sheet); rendered, then printed.
  const printSheets = async () => {
    setPreparing(true)
    try {
      const list = sheets ?? (await Promise.all(summary.learners.map((s) => getPracticeSheet(s.child_id))))
      flushSync(() => setSheets(list))
      window.print()
    } catch {
      setError(true)
    } finally {
      setPreparing(false)
    }
  }

  return (
    <>
      <main className="screen no-print">
        <p className="screen__subtitle">{t.summary.subtitle}</p>
        <h1 className="screen__title">{t.summary.title}</h1>
        <ul className="summary__list">
          {summary.learners.map((s) => {
            const learner = byId[s.child_id]
            return (
              <li key={s.child_id} className="summary__card">
                <LearnerPicture picture={learner?.picture} className="summary__picture" />
                <div className="summary__body">
                  <h2 className="summary__name">{learner?.name ?? s.child_id}</h2>
                  <p className="summary__text">{s.summary}</p>
                  <p className="summary__focus">
                    <strong>{t.summary.nextFocus}</strong>{' '}
                    {SKILL_NAMES_FIL[s.next_focus_skill] ?? s.next_focus_skill}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
        {summary.group_note && (
          <p className="summary__note">
            <strong>{t.summary.groupNote}</strong> {summary.group_note}
          </p>
        )}
        <footer className="screen__actions">
          <button type="button" className="action summary__print" onClick={printSheets} disabled={preparing}>
            <PrinterIcon />
            {preparing ? t.sheet.preparing : t.sheet.print}
          </button>
          <button type="button" className="action action--primary" onClick={onRestart}>
            {t.summary.newSession}
          </button>
        </footer>
        <Confetti count={48} />
      </main>
      {sheets && (
        <section className="print-sheets">
          {sheets.map((sheet, i) => (
            <PracticeSheet key={i} sheet={sheet} />
          ))}
        </section>
      )}
    </>
  )
}
