import './FeedbackBanner.css'

export default function FeedbackBanner({ tone, message, hint }) {
  return (
    <p className={`feedback feedback--${tone}`} role="status" aria-live="polite">
      {message}
      {hint && <span className="feedback__hint">{hint}</span>}
    </p>
  )
}
