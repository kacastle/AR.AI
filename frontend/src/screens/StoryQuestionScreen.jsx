import { useCallback, useEffect, useState } from 'react'
import FeedbackBanner from '../components/FeedbackBanner.jsx'
import SpeakerIcon from '../components/SpeakerIcon.jsx'
import TurnSwitchScreen from './TurnSwitchScreen.jsx'
import ReadAlongScreen from './ReadAlongScreen.jsx'
import Confetti from '../components/Confetti.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { playChime } from '../sfx.js'
import StarBadge from '../components/StarBadge.jsx'
import { useAudio } from '../hooks/useAudio.js'
import { getStoryTurn, submitStoryAnswer } from '../api.js'
import { t } from '../strings.js'
import './StoryQuestionScreen.css'

const SHAKE_MS = 450

export default function StoryQuestionScreen({ sessionId, learners, onDone }) {
  const [turn, setTurn] = useState(null)
  const [status, setStatus] = useState('loading')
  const [activeChild, setActiveChild] = useState(null)
  const [attempt, setAttempt] = useState(1)
  const [picked, setPicked] = useState(null)
  const [wrong, setWrong] = useState([])
  const [shaking, setShaking] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [burst, setBurst] = useState(0)
  const [reading, setReading] = useState(false) // the learner reads their own story before its questions
  const [quiz, setQuiz] = useState(null) // the learner's quiz result, after their last question
  const speaker = useAudio()

  const applyTurn = useCallback((next) => {
    setTurn(next)
    setAttempt(1)
    setPicked(null)
    setWrong([])
    setResult(null)
    setQuiz(null)
    setStatus(next ? 'ready' : 'done')
  }, [])

  useEffect(() => {
    let cancelled = false
    getStoryTurn(sessionId)
      .then((next) => !cancelled && applyTurn(next))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [sessionId, applyTurn])

  const loadNext = async () => {
    setStatus('loading')
    try {
      const next = await getStoryTurn(sessionId)
      if (next) applyTurn(next)
      else onDone()
    } catch {
      setStatus('error')
    }
  }

  if (status === 'loading') return <LoadingOverlay />
  if (status === 'error') return <main className="screen screen--center">{t.loadError}</main>
  if (status === 'done') {
    return (
      <main className="screen screen--center">
        <button type="button" className="action action--primary" onClick={onDone}>
          {t.next}
        </button>
      </main>
    )
  }

  const { question } = turn
  if (turn.child_id !== activeChild) {
    const start = () => {
      setActiveChild(turn.child_id)
      setReading(Boolean(turn.story_id))
    }
    const picture = learners.find((l) => l.id === turn.child_id)?.picture
    return <TurnSwitchScreen name={turn.child_name} picture={picture} onStart={start} />
  }

  if (reading) {
    const doneReading = () => {
      setReading(false)
      speaker.play(question.prompt_audio)
    }
    return <ReadAlongScreen key={turn.story_id} storyId={turn.story_id} onDone={doneReading} />
  }

  const finished = result?.next_action === 'next'

  const choose = async (choice) => {
    setBusy(true)
    setPicked(choice)
    try {
      const response = await submitStoryAnswer(sessionId, {
        child_id: turn.child_id,
        question_id: question.id,
        choice,
        attempt,
      })
      setResult(response)
      if (response.quiz) setQuiz(response.quiz)
      if (response.correct) {
        setBurst((b) => b + 1)
        playChime()
      }
      if (!response.correct) {
        setWrong((w) => [...w, choice])
        setShaking(choice)
        setTimeout(() => setShaking(null), SHAKE_MS)
        setAttempt((a) => a + 1)
      }
    } catch {
      setResult({ error: true })
    } finally {
      setBusy(false)
    }
  }

  const choiceClass = (choice) => {
    let name = 'action story__choice'
    if (result?.correct && choice === picked) name += ' story__choice--correct'
    if (result?.answer === choice) name += ' story__choice--answer action--glow'
    if (wrong.includes(choice)) name += ' story__choice--wrong'
    if (shaking === choice) name += ' story__choice--shake'
    return name
  }

  return (
    <main className="screen story slide-in">
      <header className="board__header">
        <span className="board__progress">{t.turnLabel(turn.turn_number)}</span>
        <div className="board__header-right">
          <span className="board__learner">{t.learnerTurn(turn.child_name)}</span>
          <StarBadge
            filled={turn.turn_number - 1 + (finished ? 1 : 0)}
            total={turn.questions_total}
            text={t.progress.questions(turn.turn_number, turn.questions_total)}
          />
        </div>
      </header>

      <h1 className="story__prompt">{question.prompt}</h1>

      <button
        type="button"
        className={`action read__listen${speaker.speaking ? ' action--speaking' : ''}`}
        onClick={() => speaker.play(question.prompt_audio)}
      >
        <SpeakerIcon />
        {t.story.listen}
      </button>

      <p className="screen__subtitle">{t.story.instruction}</p>

      <div className="story__choices" role="group" aria-label={t.story.choicesLabel}>
        {question.choices.map((choice) => (
          <button
            key={choice}
            type="button"
            className={choiceClass(choice)}
            onClick={() => choose(choice)}
            disabled={busy || finished || wrong.includes(choice)}
          >
            {choice}
          </button>
        ))}
      </div>

      <div className="board__feedback">
        {result &&
          (result.error ? (
            <FeedbackBanner tone="incorrect" message={t.loadError} />
          ) : (
            <FeedbackBanner
              tone={result.correct ? 'correct' : 'incorrect'}
              message={result.feedback.message_fil ?? t.tryAgain(turn.child_name)}
              hint={result.feedback.hint_fil}
            />
          ))}
      </div>

      {finished && quiz && (
        <section className="story__quiz" aria-live="polite">
          <StarBadge filled={quiz.correct} total={quiz.total} text={t.progress.questions(quiz.correct, quiz.total)} />
          <p className="story__quiz-level">
            {quiz.story_level > quiz.story_level_before
              ? t.quizResult.levelUp(quiz.story_level)
              : quiz.story_level < quiz.story_level_before
                ? t.quizResult.levelDown(quiz.story_level)
                : t.quizResult.levelSame(quiz.story_level)}
          </p>
          <p className="story__quiz-note">{t.quizResult.writing}</p>
        </section>
      )}

      <footer className="screen__actions">
        {finished && (
          <button type="button" className="action action--primary action--glow" onClick={loadNext}>
            {t.next}
          </button>
        )}
      </footer>
      {burst > 0 && <Confetti key={burst} />}
    </main>
  )
}
