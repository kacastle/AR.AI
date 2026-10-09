import './FeedbackBanner.css'

export default function FeedbackBanner({ tone, children }) {
  return (
    <p className={`feedback feedback--${tone}`} role="status" aria-live="polite">
      {children}
    </p>
  )
}
