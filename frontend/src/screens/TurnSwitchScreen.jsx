import { t } from '../strings.js'
import './TurnSwitchScreen.css'

const AVATAR_COLORS = ['#ff9f6b', '#7cc6ff', '#b48cff', '#7ed99a', '#ffcf5c']

function avatarColor(name) {
  let sum = 0
  for (const ch of name) sum += ch.charCodeAt(0)
  return AVATAR_COLORS[sum % AVATAR_COLORS.length]
}

function Avatar({ name }) {
  return (
    <svg className="turn-switch__avatar" viewBox="0 0 200 200" role="img" aria-label={t.turnSwitch.avatar(name)}>
      <circle cx="100" cy="100" r="96" fill={avatarColor(name)} />
      <circle cx="100" cy="112" r="62" fill="#ffe2c4" />
      <path d="M38 104 Q44 40 100 40 Q156 40 162 104 Q140 72 100 70 Q60 72 38 104Z" fill="#3b2a20" />
      <circle cx="78" cy="110" r="8" fill="#2b2b3a" />
      <circle cx="122" cy="110" r="8" fill="#2b2b3a" />
      <circle cx="64" cy="132" r="9" fill="#ff9f8a" opacity="0.7" />
      <circle cx="136" cy="132" r="9" fill="#ff9f8a" opacity="0.7" />
      <path d="M80 136 Q100 156 120 136" stroke="#2b2b3a" strokeWidth="6" fill="none" strokeLinecap="round" />
    </svg>
  )
}

export default function TurnSwitchScreen({ name, onStart }) {
  return (
    <main className="turn-switch">
      <Avatar name={name} />
      <h1 className="turn-switch__title">{t.learnerTurn(name)}</h1>
      <button type="button" className="action action--primary action--glow turn-switch__start" onClick={onStart}>
        {t.turnSwitch.start}
      </button>
    </main>
  )
}
