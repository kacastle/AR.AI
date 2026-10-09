import { useState } from 'react'
import TutorBar from './components/TutorBar.jsx'
import TutorLoginScreen from './screens/TutorLoginScreen.jsx'
import GroupSetupScreen from './screens/GroupSetupScreen.jsx'
import ReadAlongScreen from './screens/ReadAlongScreen.jsx'
import TileBoardScreen from './screens/TileBoardScreen.jsx'
import StoryQuestionScreen from './screens/StoryQuestionScreen.jsx'
import TutorSummaryScreen from './screens/TutorSummaryScreen.jsx'
import { setPhase } from './mocks/api.js'
import { t } from './strings.js'

// Session order. Steps that map to an API phase call POST /api/sessions/{id}/phase.
const STEPS = ['readAlong', 'tiles', 'stories', 'summary']
const API_PHASES = new Set(['tiles', 'stories', 'summary'])

export default function App() {
  const [step, setStep] = useState('login')
  const [group, setGroup] = useState(null)
  const [session, setSession] = useState(null)
  const [endsAt, setEndsAt] = useState(null)

  const goTo = async (next) => {
    let ends = null
    if (API_PHASES.has(next)) {
      try {
        ends = Date.parse((await setPhase(session.id, { phase: next })).ends_at)
      } catch {
        ends = null
      }
    }
    setEndsAt(ends)
    setStep(next)
  }

  const advance = () => goTo(STEPS[STEPS.indexOf(step) + 1])
  const isPhaseOver = () => endsAt !== null && Date.now() >= endsAt
  const learners = session ? group.learners.filter((l) => session.present.includes(l.id)) : []

  const startSession = (newSession, newGroup) => {
    setGroup(newGroup)
    setSession(newSession)
    setEndsAt(null)
    setStep('readAlong')
  }

  const screens = {
    login: <TutorLoginScreen onDone={() => setStep('group')} />,
    group: <GroupSetupScreen onStart={startSession} />,
    readAlong: session && <ReadAlongScreen storyId={session.read_along_story_id} onDone={advance} />,
    tiles: session && (
      <TileBoardScreen sessionId={session.id} learners={learners} isPhaseOver={isPhaseOver} onDone={advance} />
    ),
    stories: session && <StoryQuestionScreen sessionId={session.id} learners={learners} onDone={advance} />,
    summary: session && (
      <TutorSummaryScreen sessionId={session.id} learners={learners} onRestart={() => setStep('group')} />
    ),
  }

  const showBar = step in t.phases
  return (
    <div className={`app${showBar ? ' app--with-bar' : ''}`}>
      {showBar && <TutorBar key={`bar-${step}`} label={t.phases[step]} endsAt={endsAt} onSkip={advance} />}
      <div key={step}>{screens[step]}</div>
    </div>
  )
}
