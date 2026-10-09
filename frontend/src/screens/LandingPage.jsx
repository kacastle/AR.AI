import { useState } from 'react'
import logo from '../assets/logo-trim.png'
import { t } from '../strings.js'
import './LandingPage.css'

const SLIDE_MS = 320
const INK = 'currentColor'

// Built-in icons instead of emoji: emoji show as empty boxes on devices without an emoji font.
const BADGE_ICONS = [
  <svg key="lock" viewBox="0 0 24 24" aria-hidden="true">
    <rect x="5" y="10" width="14" height="11" rx="2" fill={INK} />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke={INK} strokeWidth="2.2" fill="none" />
  </svg>,
  <svg key="robot" viewBox="0 0 24 24" aria-hidden="true">
    <rect x="4" y="7" width="16" height="12" rx="3" fill={INK} />
    <path d="M12 3v4" stroke={INK} strokeWidth="2" strokeLinecap="round" />
    <circle cx="12" cy="3" r="1.6" fill={INK} />
    <circle cx="9" cy="13" r="1.8" fill="#fff" />
    <circle cx="15" cy="13" r="1.8" fill="#fff" />
  </svg>,
  <svg key="books" viewBox="0 0 24 24" aria-hidden="true">
    <rect x="3" y="4" width="5" height="16" rx="1" fill={INK} />
    <rect x="9.5" y="6" width="5" height="14" rx="1" fill={INK} opacity="0.75" />
    <path d="M16 7.5l4-1 2.6 12.6-4 1z" fill={INK} opacity="0.55" />
  </svg>,
]

const FEATURE_ICONS = [
  <svg key="story" viewBox="0 0 48 48" aria-hidden="true">
    <path d="M4 12c7-3 13-3 20 2v26c-7-5-13-5-20-2z" fill="#ffcf5c" stroke="#e0a800" strokeWidth="2" />
    <path d="M44 12c-7-3-13-3-20 2v26c7-5 13-5 20-2z" fill="#ffe08a" stroke="#e0a800" strokeWidth="2" />
    <path d="M30 6l2 4 4 .5-3 3 .8 4.5-3.8-2.2-3.8 2.2.8-4.5-3-3 4-.5z" fill="#c00d3d" />
  </svg>,
  <svg key="tiles" viewBox="0 0 48 48" aria-hidden="true">
    <rect x="3" y="14" width="18" height="20" rx="4" fill="#bfe8ff" stroke="#3a9bd9" strokeWidth="2" />
    <rect x="27" y="14" width="18" height="20" rx="4" fill="#ffe08a" stroke="#e0a800" strokeWidth="2" />
    <text x="12" y="29" fontSize="13" fontWeight="700" textAnchor="middle" fill="#2b2b3a">ba</text>
    <text x="36" y="29" fontSize="13" fontWeight="700" textAnchor="middle" fill="#2b2b3a">ta</text>
  </svg>,
  <svg key="sheet" viewBox="0 0 48 48" aria-hidden="true">
    <rect x="10" y="4" width="28" height="36" rx="3" fill="#fff" stroke="#2b2b3a" strokeWidth="2" />
    <path d="M16 13h16M16 20h16M16 27h10" stroke="#3a9bd9" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M28 34l4 4 8-9" stroke="#2fa84f" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>,
]

export default function LandingPage({ onStart }) {
  const [leaving, setLeaving] = useState(false)

  const start = () => {
    if (leaving) return
    setLeaving(true)
    setTimeout(onStart, SLIDE_MS)
  }

  return (
    <main className={`screen landing${leaving ? ' landing--leaving' : ''}`}>
      <section className="landing__hero">
        <img className="landing__logo" src={logo} alt="AR.AI" />
        <h1 className="landing__title">{t.landing.title}</h1>
        <p className="landing__subtitle">{t.landing.subtitle}</p>
      </section>

      <ul className="landing__badges">
        {t.landing.badges.map((text, i) => (
          <li key={text} className="landing__badge">
            {BADGE_ICONS[i]}
            {text}
          </li>
        ))}
      </ul>

      <ul className="landing__features">
        {t.landing.features.map((feature, i) => (
          <li key={feature.title} className="landing__card">
            {FEATURE_ICONS[i]}
            <h2 className="landing__card-title">{feature.title}</h2>
            <p className="landing__card-text">{feature.text}</p>
          </li>
        ))}
      </ul>

      <button type="button" className="action action--primary action--glow landing__cta" onClick={start}>
        {t.landing.cta}
      </button>
    </main>
  )
}
