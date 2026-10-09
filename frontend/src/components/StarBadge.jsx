import './StarBadge.css'

function StarIcon({ filled }) {
  return (
    <svg viewBox="0 0 24 24" className={`star${filled ? ' star--filled' : ''}`} aria-hidden="true">
      <path d="M12 2.5l2.9 6 6.6.8-4.9 4.5 1.3 6.5L12 17l-5.9 3.3 1.3-6.5L2.5 9.3l6.6-.8z" />
    </svg>
  )
}

// With `total`: one star per step, `filled` of them gold. Without: a single star and the text.
export default function StarBadge({ filled, total, text }) {
  const stars = total ? Array.from({ length: total }, (_, i) => i < filled) : [true]
  return (
    <div className="star-badge">
      <span key={filled} className="star-badge__stars">
        {stars.map((on, i) => (
          <StarIcon key={i} filled={on} />
        ))}
      </span>
      <span className="star-badge__text">{text}</span>
    </div>
  )
}
