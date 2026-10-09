import { useEffect, useState } from 'react'
import { t } from '../strings.js'

const SLIDE_MS = 320

// Built-in icons instead of emoji: emoji show as empty boxes on devices without an emoji font.
const FEATURE_ICONS = [
  <svg key="story" viewBox="0 0 48 48" width="44" height="44" aria-hidden="true" style={{ flexShrink: 0 }}>
    <path d="M4 12c7-3 13-3 20 2v26c-7-5-13-5-20-2z" fill="#ffcf5c" stroke="#e0a800" strokeWidth="2" />
    <path d="M44 12c-7-3-13-3-20 2v26c7-5 13-5 20-2z" fill="#ffe08a" stroke="#e0a800" strokeWidth="2" />
    <path d="M30 6l2 4 4 .5-3 3 .8 4.5-3.8-2.2-3.8 2.2.8-4.5-3-3 4-.5z" fill="#c00d3d" />
  </svg>,
  <svg key="tiles" viewBox="0 0 48 48" width="44" height="44" aria-hidden="true" style={{ flexShrink: 0 }}>
    <rect x="3" y="14" width="18" height="20" rx="4" fill="#bfe8ff" stroke="#3a9bd9" strokeWidth="2" />
    <rect x="27" y="14" width="18" height="20" rx="4" fill="#ffe08a" stroke="#e0a800" strokeWidth="2" />
    <text x="12" y="29" fontSize="13" fontWeight="700" textAnchor="middle" fill="#2b2b3a">ba</text>
    <text x="36" y="29" fontSize="13" fontWeight="700" textAnchor="middle" fill="#2b2b3a">ta</text>
  </svg>,
  <svg key="sheet" viewBox="0 0 48 48" width="44" height="44" aria-hidden="true" style={{ flexShrink: 0 }}>
    <rect x="10" y="4" width="28" height="36" rx="3" fill="#fff" stroke="#2b2b3a" strokeWidth="2" />
    <path d="M16 13h16M16 20h16M16 27h10" stroke="#3a9bd9" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M28 34l4 4 8-9" stroke="#2fa84f" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>,
]

const CREAM = '#FAF6E9'
const SLATE = '#1E3A5F'
const ORANGE = '#F28C28'
const GREEN = '#2FA84F'

const styles = {
  page: {
    minHeight: '100vh',
    background: CREAM,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'flex-start',
    padding: '6vh 16px 48px',
    boxSizing: 'border-box',
    textAlign: 'center',
    overflowX: 'hidden',
  },
  infoButton: {
    position: 'fixed',
    top: 20,
    left: 20,
    width: 52,
    height: 52,
    borderRadius: '50%',
    border: '3px solid #fff',
    background: ORANGE,
    color: '#fff',
    fontFamily: 'Georgia, "Times New Roman", serif',
    fontStyle: 'italic',
    fontWeight: 700,
    fontSize: 26,
    lineHeight: 1,
    cursor: 'pointer',
    boxShadow: '0 6px 16px rgba(0, 0, 0, 0.22)',
    zIndex: 10,
  },
  logo: {
    width: 380,
    maxWidth: '85vw',
    height: 'auto',
    display: 'block',
    margin: 0,
  },
  title: {
    margin: '5px 0 0',
    color: SLATE,
    fontWeight: 800,
    fontSize: 'clamp(15px, 3.6vw, 34px)',
    whiteSpace: 'nowrap',
    lineHeight: 1.2,
  },
  subtitle: {
    margin: '14px auto 0',
    maxWidth: 620,
    color: '#6B7280',
    fontSize: 'clamp(16px, 2.2vw, 20px)',
    lineHeight: 1.5,
  },
  cta: {
    marginTop: 32,
    padding: '20px 44px',
    border: 'none',
    borderRadius: 999,
    background: GREEN,
    color: '#fff',
    fontFamily: 'inherit',
    fontWeight: 800,
    fontSize: 'clamp(18px, 2.6vw, 24px)',
    cursor: 'pointer',
    boxShadow: '0 6px 0 #1F7A37, 0 10px 20px rgba(0, 0, 0, 0.12)',
  },
  backdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15, 23, 42, 0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    zIndex: 20,
  },
  modal: {
    position: 'relative',
    width: '100%',
    maxWidth: 560,
    maxHeight: '90vh',
    overflowY: 'auto',
    background: '#fff',
    borderRadius: 24,
    padding: '32px 24px 24px',
    boxShadow: '0 24px 60px rgba(0, 0, 0, 0.3)',
    textAlign: 'left',
    boxSizing: 'border-box',
  },
  close: {
    position: 'absolute',
    top: 12,
    right: 12,
    width: 40,
    height: 40,
    border: 'none',
    borderRadius: '50%',
    background: '#F1F5F9',
    color: SLATE,
    fontSize: 20,
    fontWeight: 700,
    cursor: 'pointer',
  },
  modalTitle: { margin: '0 40px 20px 0', color: SLATE, fontSize: 24, fontWeight: 800 },
  cards: { listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 14 },
  card: {
    display: 'flex',
    gap: 14,
    alignItems: 'flex-start',
    padding: 16,
    borderRadius: 16,
    background: CREAM,
    border: '1px solid #EFE6CC',
  },
  cardTitle: { margin: 0, color: SLATE, fontSize: 18, fontWeight: 800 },
  cardText: { margin: '6px 0 0', color: '#4B5563', fontSize: 16, lineHeight: 1.45 },
}

const css = `
@keyframes landing-float { 0%, 100% { transform: translateY(0) } 50% { transform: translateY(-10px) } }
@keyframes landing-fade { from { opacity: 0; transform: translateY(12px) } to { opacity: 1; transform: none } }
.landing-logo { animation: landing-float 3.2s ease-in-out infinite; }
.landing-page { animation: landing-fade 400ms ease-out; transition: opacity ${SLIDE_MS}ms ease, transform ${SLIDE_MS}ms ease; }
.landing-page--leaving { opacity: 0; transform: translateX(-40px); }
.landing-cta { transition: transform 200ms ease, box-shadow 200ms ease; }
.landing-cta:hover { transform: translateY(-3px); box-shadow: 0 9px 0 #1F7A37, 0 0 0 6px rgba(47, 168, 79, 0.18), 0 12px 32px rgba(47, 168, 79, 0.55); }
.landing-cta:active { transform: translateY(2px); box-shadow: 0 3px 0 #1F7A37; }
.landing-cta:focus-visible, .landing-info:focus-visible, .landing-close:focus-visible { outline: 4px solid #3A9BD9; outline-offset: 3px; }
.landing-info { transition: transform 200ms ease; }
.landing-info:hover { transform: scale(1.08); }
.landing-modal { animation: landing-fade 220ms ease-out; }
@media (prefers-reduced-motion: reduce) {
  .landing-logo, .landing-page, .landing-modal { animation: none; }
}
`

export default function LandingPage({ onStart }) {
  const [leaving, setLeaving] = useState(false)
  const [infoOpen, setInfoOpen] = useState(false)

  useEffect(() => {
    if (!infoOpen) return undefined
    const onKey = (e) => e.key === 'Escape' && setInfoOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [infoOpen])

  const start = () => {
    if (leaving) return
    setLeaving(true)
    setTimeout(onStart, SLIDE_MS)
  }

  return (
    <main className={`landing-page${leaving ? ' landing-page--leaving' : ''}`} style={styles.page}>
      <style>{css}</style>

      <button
        type="button"
        className="landing-info"
        style={styles.infoButton}
        onClick={() => setInfoOpen(true)}
        aria-label={t.landing.infoLabel}
        aria-haspopup="dialog"
      >
        i
      </button>

      <img className="landing-logo" src="/logo.png" alt="AR.AI" style={styles.logo} />
      <h1 style={styles.title}>{t.landing.title}</h1>
      <p style={styles.subtitle}>{t.landing.subtitle}</p>

      <button type="button" className="landing-cta" style={styles.cta} onClick={start}>
        {t.landing.cta}
      </button>

      {infoOpen && (
        <div style={styles.backdrop} onClick={() => setInfoOpen(false)}>
          <section
            className="landing-modal"
            style={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="landing-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="landing-close"
              style={styles.close}
              onClick={() => setInfoOpen(false)}
              aria-label={t.landing.close}
              autoFocus
            >
              ✕
            </button>
            <h2 id="landing-modal-title" style={styles.modalTitle}>
              {t.landing.modalTitle}
            </h2>
            <ul style={styles.cards}>
              {t.landing.features.map((feature, i) => (
                <li key={feature.title} style={styles.card}>
                  {FEATURE_ICONS[i]}
                  <div>
                    <h3 style={styles.cardTitle}>{feature.title}</h3>
                    <p style={styles.cardText}>{feature.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </main>
  )
}
