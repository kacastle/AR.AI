import { useEffect, useState } from 'react'
import './Confetti.css'

const COLORS = ['#ffcf5c', '#ff8a3d', '#7cc6ff', '#7ed99a', '#b48cff', '#ff7a8a']
const DURATION_MS = 1800

function makePieces(count) {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2 + Math.random() * 0.5
    const distance = 120 + Math.random() * 180
    return {
      id: i,
      star: i % 3 === 0,
      color: COLORS[i % COLORS.length],
      dx: Math.cos(angle) * distance,
      dy: Math.sin(angle) * distance * 0.8 - 80,
      rot: Math.random() * 540 - 270,
      delay: Math.random() * 120,
      size: 12 + Math.random() * 14,
    }
  })
}

// One burst of stars and confetti from the middle of the screen. Remount (new key) to replay.
export default function Confetti({ count = 28 }) {
  const [pieces] = useState(() => makePieces(count))
  const [done, setDone] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setDone(true), DURATION_MS)
    return () => clearTimeout(id)
  }, [])

  if (done) return null
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p) => (
        <span
          key={p.id}
          className={`confetti__piece${p.star ? ' confetti__piece--star' : ''}`}
          style={{
            '--dx': `${p.dx}px`,
            '--dy': `${p.dy}px`,
            '--rot': `${p.rot}deg`,
            '--size': `${p.size}px`,
            '--color': p.color,
            animationDelay: `${p.delay}ms`,
          }}
        />
      ))}
    </div>
  )
}
