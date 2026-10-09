import { useEffect, useRef } from 'react'
import { t } from '../strings.js'
import './FeedbackOverlay.css'

function HelperFace() {
  return (
    <svg className="overlay__face" viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="50" cy="50" r="46" fill="#ffcf5c" stroke="#e0a800" strokeWidth="4" />
      <circle cx="35" cy="42" r="6" fill="#2b2b3a" />
      <circle cx="65" cy="42" r="6" fill="#2b2b3a" />
      <circle cx="26" cy="60" r="7" fill="#ff9f8a" opacity="0.7" />
      <circle cx="74" cy="60" r="7" fill="#ff9f8a" opacity="0.7" />
      <path d="M34 62 Q50 76 66 62" stroke="#2b2b3a" strokeWidth="5" fill="none" strokeLinecap="round" />
    </svg>
  )
}

// Wrong-answer pop-up. Uses the API's Filipino feedback when it sends one; the API
// leaves feedback null for attempts 1-3, so those use a hint line for hint.kind.
export default function FeedbackOverlay({ response, name, onRetry, onShowAnswer, onListen }) {
  const actionRef = useRef(null)
  const showAnswer = response.next_action === 'show_answer'
  const title = response.feedback.message_fil ?? t.overlay.title
  const body =
    response.feedback.hint_fil ?? t.overlay.hints[response.hint?.kind] ?? t.tryAgain(name)

  useEffect(() => {
    actionRef.current?.focus()
  }, [])

  return (
    <div className="overlay">
      <div
        className="overlay__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="overlay-title"
        aria-describedby="overlay-body"
      >
        <HelperFace />
        <h2 id="overlay-title" className="overlay__title">
          {title}
        </h2>
        <p id="overlay-body" className="overlay__body">
          {body}
        </p>
        <div className="overlay__actions">
          {showAnswer ? (
            <button
              ref={actionRef}
              type="button"
              className="action action--primary"
              onClick={onShowAnswer}
            >
              {t.overlay.showAnswer}
            </button>
          ) : (
            <>
              {response.hint?.audio && (
                <button type="button" className="action" onClick={() => onListen(response.hint.audio)}>
                  {t.overlay.listenAgain}
                </button>
              )}
              <button
                ref={actionRef}
                type="button"
                className="action action--primary"
                onClick={onRetry}
              >
                {t.overlay.retry}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
