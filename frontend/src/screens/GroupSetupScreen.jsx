import { useEffect, useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { createSession, getDemoGroup } from '../api.js'
import { t } from '../strings.js'
import './GroupSetupScreen.css'

export default function GroupSetupScreen({ onStart }) {
  const [group, setGroup] = useState(null)
  const [present, setPresent] = useState(() => new Set())
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    getDemoGroup()
      .then((g) => {
        if (cancelled) return
        setGroup(g)
        setPresent(new Set(g.learners.map((l) => l.id)))
      })
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <main className="screen screen--center">{t.loadError}</main>
  if (!group) return <LoadingOverlay />

  const toggle = (id) =>
    setPresent((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const start = async () => {
    setBusy(true)
    try {
      // `present` keeps the group's order, which is the turn order.
      const ids = group.learners.filter((l) => present.has(l.id)).map((l) => l.id)
      onStart(await createSession({ group_id: group.id, present: ids }), group)
    } catch {
      setError(true)
    }
  }

  return (
    <main className="screen">
      <p className="screen__subtitle">{t.group.greeting(group.tutor_name)}</p>
      <h1 className="screen__title">{t.group.question}</h1>
      <ul className="group__list">
        {group.learners.map((learner) => {
          const here = present.has(learner.id)
          return (
            <li key={learner.id}>
              <button
                type="button"
                className={`group__learner${here ? ' group__learner--present' : ''}`}
                aria-pressed={here}
                onClick={() => toggle(learner.id)}
              >
                <LearnerPicture picture={learner.picture} className="group__picture" />
                <span className="group__name">{learner.name}</span>
                <span className="group__status">{here ? t.group.present : t.group.absent}</span>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="group__hint" role="status">
        {present.size === 0 ? t.group.needOne : t.group.count(present.size)}
      </p>
      <footer className="screen__actions">
        <button
          type="button"
          className="action action--primary"
          onClick={start}
          disabled={present.size === 0 || busy}
        >
          {t.group.start}
        </button>
      </footer>
      {busy && <LoadingOverlay label={t.loadingSession} />}
    </main>
  )
}
