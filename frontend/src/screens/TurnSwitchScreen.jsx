import LearnerPicture from '../components/LearnerPicture.jsx'
import { t } from '../strings.js'
import './TurnSwitchScreen.css'

export default function TurnSwitchScreen({ name, picture, onStart }) {
  return (
    <main className="turn-switch">
      <LearnerPicture picture={picture} label={t.turnSwitch.avatar(name)} className="turn-switch__avatar" />
      <h1 className="turn-switch__title">{t.learnerTurn(name)}</h1>
      <button type="button" className="action action--primary action--glow turn-switch__start" onClick={onStart}>
        {t.turnSwitch.start}
      </button>
    </main>
  )
}
