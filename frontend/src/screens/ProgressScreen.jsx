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

// GET /api/children/{id}/profile: what the learner knows, how they learn, and how they are doing over time.
export default function ProgressScreen({ childId, picture, onBack }) {
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
          {t.profile.back}
        </button>
      </footer>
    </main>
  )
}
