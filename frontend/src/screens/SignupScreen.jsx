import { useEffect, useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { createGroup, getInterests } from '../api.js'
import { t } from '../strings.js'
import './SignupScreen.css'

const PICTURES = ['cat', 'dog', 'star']
const MAX_LEARNERS = 5 // rules.json session.max_learners
const MAX_INTERESTS = 3 // rules.json personalization.max_interests_per_learner

const blank = (i) => ({ name: '', picture: PICTURES[i % PICTURES.length], interests: [], diagnostic: true })

// The tutor signs up the learners first: name, picture and interests. Interests theme each learner's
// stories, lessons and words; the diagnostic finds where each learner starts.
export default function SignupScreen({ onDone, onCancel }) {
  const [catalog, setCatalog] = useState(null)
  const [tutor, setTutor] = useState('')
  const [learners, setLearners] = useState([blank(0)])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    getInterests()
      .then((list) => !cancelled && setCatalog(list))
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <main className="screen screen--center">{t.loadError}</main>
  if (!catalog) return <LoadingOverlay />

  const update = (i, change) => setLearners((all) => all.map((l, k) => (k === i ? { ...l, ...change } : l)))
  const toggleInterest = (i, id) => {
    const mine = learners[i].interests
    if (mine.includes(id)) update(i, { interests: mine.filter((x) => x !== id) })
    else if (mine.length < MAX_INTERESTS) update(i, { interests: [...mine, id] })
  }
  const ready = tutor.trim() && learners.every((l) => l.name.trim() && l.interests.length > 0)

  const save = async () => {
    setBusy(true)
    try {
      const group = await createGroup({
        tutor_name: tutor.trim(),
        learners: learners.map((l) => ({
          name: l.name.trim(),
          picture: l.picture,
          profile: 'low_emergent', // the diagnostic sets the real profile
          interests: l.interests,
          diagnostic: l.diagnostic,
        })),
      })
      onDone(group)
    } catch {
      setError(true)
      setBusy(false)
    }
  }

  return (
    <main className="screen signup slide-in">
      <p className="screen__subtitle">{t.signup.subtitle}</p>
      <h1 className="screen__title">{t.signup.title}</h1>

      <label className="signup__field">
        <span>{t.signup.tutorName}</span>
        <input value={tutor} onChange={(e) => setTutor(e.target.value)} maxLength={40} />
      </label>

      <ol className="signup__learners">
        {learners.map((l, i) => (
          <li key={i} className="signup__card pop-in">
            <div className="signup__row">
              <LearnerPicture picture={l.picture} className="signup__avatar" />
              <label className="signup__field signup__field--grow">
                <span>{t.signup.childName(i + 1)}</span>
                <input
                  value={l.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  maxLength={20}
                  placeholder={t.signup.firstNameOnly}
                />
              </label>
              {learners.length > 1 && (
                <button
                  type="button"
                  className="action signup__remove"
                  onClick={() => setLearners((all) => all.filter((_, k) => k !== i))}
                  aria-label={t.signup.remove(l.name || i + 1)}
                >
                  ✕
                </button>
              )}
            </div>

            <div className="signup__pictures" role="radiogroup" aria-label={t.signup.picture}>
              {PICTURES.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={l.picture === p}
                  className={`signup__picture${l.picture === p ? ' signup__picture--on' : ''}`}
                  onClick={() => update(i, { picture: p })}
                >
                  <LearnerPicture picture={p} />
                </button>
              ))}
            </div>

            <p className="signup__label">{t.signup.interests(l.interests.length, MAX_INTERESTS)}</p>
            <div className="signup__chips">
              {catalog.map((c) => {
                const on = l.interests.includes(c.id)
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={on}
                    className={`signup__chip${on ? ' signup__chip--on' : ''}`}
                    onClick={() => toggleInterest(i, c.id)}
                    disabled={!on && l.interests.length >= MAX_INTERESTS}
                  >
                    <span aria-hidden="true">{c.icon}</span> {c.label_fil}
                  </button>
                )
              })}
            </div>

            <label className="signup__check">
              <input
                type="checkbox"
                checked={l.diagnostic}
                onChange={(e) => update(i, { diagnostic: e.target.checked })}
              />
              {t.signup.diagnostic}
            </label>
          </li>
        ))}
      </ol>

      {learners.length < MAX_LEARNERS && (
        <button type="button" className="action signup__add" onClick={() => setLearners((all) => [...all, blank(all.length)])}>
          + {t.signup.addChild}
        </button>
      )}

      <p className="group__hint" role="status">
        {ready ? t.signup.ready(learners.length) : t.signup.needed}
      </p>
      <footer className="screen__actions">
        {onCancel && (
          <button type="button" className="action" onClick={onCancel}>
            {t.signup.cancel}
          </button>
        )}
        <button type="button" className="action action--primary" onClick={save} disabled={!ready || busy}>
          {t.signup.save}
        </button>
      </footer>
      {busy && <LoadingOverlay label={t.loading} />}
    </main>
  )
}
