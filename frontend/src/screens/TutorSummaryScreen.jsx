import { useEffect, useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import { SKILL_NAMES_FIL, getSummary } from '../mocks/api.js'
import { t } from '../strings.js'
import './TutorSummaryScreen.css'

export default function TutorSummaryScreen({ sessionId, learners, onRestart }) {
  const [summary, setSummary] = useState(null)
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

  return (
    <main className="screen">
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
        <button type="button" className="action action--primary" onClick={onRestart}>
          {t.summary.newSession}
        </button>
      </footer>
    </main>
  )
}
