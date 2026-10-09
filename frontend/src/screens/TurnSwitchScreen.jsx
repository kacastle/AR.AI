import { useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import { t } from '../strings.js'
import './TurnSwitchScreen.css'

const SLIDE_MS = 320

// Slides in from the right; on "Magsimula" it slides out to the left before the turn starts.
export default function TurnSwitchScreen({ name, picture, onStart }) {
  const [leaving, setLeaving] = useState(false)

  const start = () => {
    if (leaving) return
    setLeaving(true)
    setTimeout(onStart, SLIDE_MS)
  }

  return (
    <main className={`turn-switch${leaving ? ' turn-switch--leaving' : ''}`}>
      <LearnerPicture picture={picture} label={t.turnSwitch.avatar(name)} className="turn-switch__avatar" />
      <h1 className="turn-switch__title">{t.learnerTurn(name)}</h1>
      <button type="button" className="action action--primary action--glow turn-switch__start" onClick={start}>
        {t.turnSwitch.start}
      </button>
    </main>
  )
}
