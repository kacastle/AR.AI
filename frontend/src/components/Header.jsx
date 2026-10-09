import logo from '../assets/logo-trim.png'
import { highContrast, sfxMuted, useToggle } from '../preferences.js'
import { t } from '../strings.js'
import './Header.css'

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2l8 3v6c0 5-3.4 9.4-8 11-4.6-1.6-8-6-8-11V5z" fill="currentColor" />
      <path d="M8 12l3 3 5-6" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SoundIcon({ muted }) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor" />
      {muted ? (
        <path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      ) : (
        <path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
      )}
    </svg>
  )
}

function ContrastIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />
    </svg>
  )
}

// Shown on every screen: privacy pill, logo, and the sound / contrast toggles.
export default function Header() {
  const muted = useToggle(sfxMuted)
  const contrast = useToggle(highContrast)
  return (
    <header className="app-header">
      <p className="app-header__privacy">
        <ShieldIcon />
        {t.header.privacy}
      </p>
      <div className="app-header__logo-plate">
        <img className="app-header__logo" src={logo} alt={t.header.logoAlt} />
      </div>
      <div className="app-header__tools">
        <button
          type="button"
          className="icon-toggle"
          aria-pressed={!muted}
          aria-label={t.header.sound}
          title={t.header.sound}
          onClick={() => sfxMuted.set(!muted)}
        >
          <SoundIcon muted={muted} />
        </button>
        <button
          type="button"
          className={`icon-toggle${contrast ? ' icon-toggle--on' : ''}`}
          aria-pressed={contrast}
          aria-label={t.header.contrast}
          title={t.header.contrast}
          onClick={() => highContrast.set(!contrast)}
        >
          <ContrastIcon />
        </button>
      </div>
    </header>
  )
}
