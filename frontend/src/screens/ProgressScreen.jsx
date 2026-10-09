import { useEffect, useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import StarBadge from '../components/StarBadge.jsx'
import { getProfile } from '../api.js'
import { t } from '../strings.js'
import './ProgressScreen.css'

function SkillList({ title, skills }) {
  return (
    <section className="progress__block">
      <h2 className="progress__heading">{title}</h2>
      {skills.length ? (
        <ul className="progress__skills">
          {skills.map((s) => (
            <li key={s.id} className="progress__skill">
              <span>{s.name}</span>
              <span className="progress__bar" aria-hidden="true">
                <span style={{ width: `${Math.round(s.score * 100)}%` }} />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="progress__none">{t.profile.none}</p>
      )}
    </section>
  )
}

// Skills mastered after each session: one series, so no legend; the title names it. Hover a point for its numbers.
function HistoryChart({ history, total }) {
  const W = 560
  const H = 200
  const pad = { l: 36, r: 24, t: 16, b: 32 }
  const n = history.length
  const x = (i) => pad.l + (n === 1 ? (W - pad.l - pad.r) / 2 : (i * (W - pad.l - pad.r)) / (n - 1))
  // Scaled to the data so growth is visible; the last label still says how many of all skills.
  const top = Math.min(total, Math.max(4, Math.ceil(Math.max(...history.map((h) => h.mastered_count)) * 1.25)))
  const y = (v) => pad.t + (1 - v / top) * (H - pad.t - pad.b)
  const points = history.map((h, i) => `${x(i)},${y(h.mastered_count)}`).join(' ')
  const ticks = [0, Math.round(top / 2), top]
  const last = history[n - 1]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img"
      aria-label={t.profile.chartLabel(last.mastered_count, total, n)}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="#E5E7EB" strokeWidth="1" />
          <text x={pad.l - 8} y={y(v) + 4} fontSize="14" textAnchor="end" fill="#6B7280">{v}</text>
        </g>
      ))}
      {history.map((h, i) => (
        <text key={h.session_id} x={x(i)} y={H - 10} fontSize="14" textAnchor="middle" fill="#6B7280">
          {h.date.slice(5)}
        </text>
      ))}
      {n > 1 && <polyline points={points} fill="none" stroke="#2FA84F" strokeWidth="2" strokeLinejoin="round" />}
      {history.map((h, i) => (
        <g key={h.session_id}>
          <circle cx={x(i)} cy={y(h.mastered_count)} r="14" fill="transparent">
            <title>{t.profile.chartPoint(h.date, h.mastered_count, total, h.accuracy)}</title>
          </circle>
          <circle cx={x(i)} cy={y(h.mastered_count)} r="5" fill="#2FA84F" stroke="#fff" strokeWidth="2"
            pointerEvents="none" />
        </g>
      ))}
      <text x={x(n - 1)} y={y(last.mastered_count) - 12} fontSize="15" fontWeight="700" textAnchor="middle"
        fill="#1F2937">{last.mastered_count}/{total}</text>
    </svg>
  )
}

// Every skill in teaching order (vowels first): a bar for the score, and a check mark when mastered.
function Ladder({ ladder }) {
  return (
    <ol className="progress__skills" style={{ listStyle: 'none', padding: 0 }}>
      {ladder.map((s) => (
        <li key={s.skill_id} className="progress__skill">
          <span>
            {s.mastered ? '✓ ' : ''}
            {s.name_fil} <span style={{ color: '#6B7280' }}>({Math.round(s.score * 100)}%)</span>
          </span>
          <span className="progress__bar" aria-hidden="true">
            <span style={{ width: `${Math.round(s.score * 100)}%` }} />
          </span>
        </li>
      ))}
    </ol>
  )
}

// GET /api/children/{id}/profile: what the learner knows, how they learn, and how they are doing over time.
export default function ProgressScreen({ childId, picture, onBack, backLabel }) {
  const [p, setP] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    getProfile(childId)
      .then((profile) => !cancelled && setP(profile))
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [childId])

  if (error) return <main className="screen screen--center">{t.loadError}</main>
  if (!p) return <LoadingOverlay />

  return (
    <main className="screen progress slide-in">
      <p className="screen__subtitle">{t.profile.forParents}</p>
      <header className="progress__header">
        <LearnerPicture picture={picture} className="summary__picture" />
        <h1 className="screen__title">{t.profile.title(p.name)}</h1>
        <StarBadge filled={p.stars} text={t.profile.stars(p.stars, p.streak)} />
      </header>

      <dl className="progress__facts">
        <div>
          <dt>{t.profile.interests}</dt>
          <dd>{p.interests.length ? p.interests.map((i) => `${i.icon} ${i.label}`).join(', ') : t.profile.none}</dd>
        </div>
        <div>
          <dt>{t.profile.level}</dt>
          <dd>{p.story_level}</dd>
        </div>
        <div>
          <dt>{t.profile.pace}</dt>
          <dd>{p.pace ? t.profile.paces[p.pace] : t.profile.none}</dd>
        </div>
        {p.diagnostic && (
          <div>
            <dt>{t.profile.diagnostic}</dt>
            <dd>{t.profile.diagnostics[p.diagnostic]}</dd>
          </div>
        )}
        <div>
          <dt>{t.profile.now}</dt>
          <dd>{p.current_skill.name}</dd>
        </div>
      </dl>

      {p.history?.length > 0 && (
        <section className="progress__block" style={{ width: '100%', maxWidth: 640 }}>
          <h2 className="progress__heading">{t.profile.chartTitle}</h2>
          <HistoryChart history={p.history} total={p.ladder?.length || 1} />
        </section>
      )}

      {p.ladder?.length > 0 && (
        <section className="progress__block" style={{ width: '100%', maxWidth: 640 }}>
          <h2 className="progress__heading">{t.profile.ladder}</h2>
          <Ladder ladder={p.ladder} />
        </section>
      )}

      <div className="progress__grid">
        <SkillList title={t.profile.mastered} skills={p.mastered} />
        <SkillList title={t.profile.strengths} skills={p.strengths} />
        <SkillList title={t.profile.needsWork} skills={p.needs_work} />
      </div>

      <section className="progress__block">
        <h2 className="progress__heading">{t.profile.methods}</h2>
        {p.methods.length ? (
          <ul className="progress__methods">
            {p.methods.map((m, i) => (
              <li key={i}>
                <strong>{m.mistake}:</strong> {m.method_description}{' '}
                <em>
                  ({m.worked === null ? t.profile.running : m.worked ? t.profile.worked : t.profile.notYet},{' '}
                  {m.correct}/{m.total})
                </em>
              </li>
            ))}
          </ul>
        ) : (
          <p className="progress__none">{t.profile.none}</p>
        )}
      </section>

      <section className="progress__block">
        <h2 className="progress__heading">{t.profile.sessions}</h2>
        {p.sessions.length ? (
          <ol className="progress__sessions">
            {p.sessions.map((s) => (
              <li key={s.session_id}>
                <span>{s.date}</span>
                <span className="progress__bar" aria-hidden="true">
                  <span style={{ width: `${s.total ? Math.round((100 * s.correct) / s.total) : 0}%` }} />
                </span>
                <span>
                  {s.correct}/{s.total}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="progress__none">{t.profile.none}</p>
        )}
      </section>

      <footer className="screen__actions">
        <button type="button" className="action action--primary" onClick={onBack}>
          {backLabel ?? t.profile.back}
        </button>
      </footer>
    </main>
  )
}
