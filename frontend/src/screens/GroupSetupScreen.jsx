import { useEffect, useState } from 'react'
import LearnerPicture from '../components/LearnerPicture.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import SignupScreen from './SignupScreen.jsx'
import { createGroup, createSession, forgetGroup, getLearners, getSavedGroup } from '../api.js'
import { t } from '../strings.js'
import './GroupSetupScreen.css'

// Learners who already used AR.AI on this laptop: their skills, diagnostic and story level are saved.
function ReturningPicker({ learners, onUse, onSignUp, onBack }) {
  const [picked, setPicked] = useState(() => new Set())
  const toggle = (id) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  return (
    <main className="screen">
      <p className="screen__subtitle">{t.returning.subtitle}</p>
      <h1 className="screen__title">{t.returning.title}</h1>
      {learners.length === 0 && <p className="group__hint">{t.returning.none}</p>}
      <ul className="group__list">
        {learners.map((l) => {
          const on = picked.has(l.id)
          return (
            <li key={l.id}>
              <button
                type="button"
                className={`group__learner${on ? ' group__learner--present' : ''}`}
                aria-pressed={on}
                onClick={() => toggle(l.id)}
              >
                <LearnerPicture picture={l.picture} className="group__picture" />
                <span className="group__name">{l.name}</span>
                <span className="group__status" style={{ fontSize: 14, lineHeight: 1.4 }}>
                  {t.returning.level(l.story_level)} · {t.returning.mastered(l.mastered_count)}
                  <br />
                  {l.current_skill_fil}
                  <br />
                  {t.returning.last(l.last_session)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      <footer className="screen__actions">
        {onBack && (
          <button type="button" className="action" onClick={onBack}>
            {t.returning.back}
          </button>
        )}
        <button type="button" className="action" onClick={onSignUp}>
          {t.returning.signUp}
        </button>
        <button
          type="button"
          className="action action--primary"
          disabled={picked.size === 0}
          onClick={() => onUse(learners.filter((l) => picked.has(l.id)).map((l) => l.id))}
        >
          {t.returning.use(picked.size)}
        </button>
      </footer>
    </main>
  )
}

export default function GroupSetupScreen({ onStart }) {
  const [group, setGroup] = useState(null)
  const [present, setPresent] = useState(() => new Set())
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [signup, setSignup] = useState(false) // no group yet, or the tutor signs up a new one
  const [saved, setSaved] = useState(null) // every saved learner (GET /api/learners), for the returning picker
  const [picking, setPicking] = useState(false)

  const applyGroup = (g) => {
    setGroup(g)
    setPresent(new Set(g.learners.map((l) => l.id)))
    setSignup(false)
  }

  useEffect(() => {
    let cancelled = false
    getSavedGroup()
      .then((g) => {
        if (cancelled) return
        if (g) return applyGroup(g)
        // No group on this laptop yet: returning learners first when there are any, else sign-up.
        return getLearners().then((all) => {
          if (cancelled) return
          setSaved(all)
          if (all.length) setPicking(true)
          else setSignup(true)
        })
      })
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <main className="screen screen--center">{t.loadError}</main>

  const openPicker = () =>
    getLearners()
      .then((all) => {
        setSaved(all)
        setPicking(true)
      })
      .catch(() => setError(true))

  const useReturning = async (ids) => {
    setBusy(true)
    try {
      const g = await createGroup({ tutor_name: group?.tutor_name ?? 'Tutor', learners: [], existing_child_ids: ids })
      setPicking(false)
      applyGroup(g)
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  if (picking && saved) {
    return (
      <ReturningPicker
        learners={saved}
        onUse={useReturning}
        onSignUp={() => {
          setPicking(false)
          setSignup(true)
        }}
        onBack={group ? () => setPicking(false) : null}
      />
    )
  }
  if (signup) {
    const cancel = group ? () => setSignup(false) : null
    return <SignupScreen onDone={applyGroup} onCancel={cancel} />
  }
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
          className="action"
          onClick={() => {
            forgetGroup()
            setSignup(true)
          }}
        >
          {t.signup.newGroup}
        </button>
        <button type="button" className="action" onClick={openPicker}>
          {t.returning.open}
        </button>
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
