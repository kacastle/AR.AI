import { useEffect, useState } from 'react'
import { t } from '../strings.js'
import './TutorBar.css'

function formatSeconds(total) {
  const m = Math.floor(total / 60)
  const s = String(total % 60).padStart(2, '0')
  return `${m}:${s}`
}

// Tutor-only strip: phase name, time left (from the API's ends_at) and a skip button.
export default function TutorBar({ label, endsAt, onSkip }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!endsAt) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [endsAt])

  const left = endsAt ? Math.max(0, Math.ceil((endsAt - now) / 1000)) : null

  return (
    <div className="tutor-bar">
      <span className="tutor-bar__label">
        {t.tutorBar.tutor} · {label}
      </span>
      {left !== null && (
        <span className={`tutor-bar__time${left === 0 ? ' tutor-bar__time--up' : ''}`}>
          {left === 0 ? t.tutorBar.timeUp : t.tutorBar.timeLeft(formatSeconds(left))}
        </span>
      )}
      <button type="button" className="tutor-bar__skip" onClick={onSkip}>
        {t.tutorBar.skip}
      </button>
    </div>
  )
}
