import { useCallback, useEffect, useState } from 'react'
import Tile from '../components/Tile.jsx'
import Slot from '../components/Slot.jsx'
import FeedbackBanner from '../components/FeedbackBanner.jsx'
import Picture from '../components/Picture.jsx'
import StarIcon from '../components/StarIcon.jsx'
import { getNextTurn, submitAnswer } from '../mocks/api.js'
import { t } from '../strings.js'
import './TileBoardScreen.css'

export default function TileBoardScreen() {
  const [turn, setTurn] = useState(null)
  const [slots, setSlots] = useState([])
  const [result, setResult] = useState(null)
  const [stars, setStars] = useState(0)
  const [status, setStatus] = useState('loading')

  const applyTurn = useCallback((next) => {
    setTurn(next)
    setSlots(Array(next.slot_count).fill(null))
    setResult(null)
    setStatus('ready')
  }, [])

  const fetchTurn = useCallback(
    (afterTurnId) =>
      getNextTurn(afterTurnId)
        .then(applyTurn)
        .catch(() => setStatus('error')),
    [applyTurn],
  )

  useEffect(() => {
    let cancelled = false
    getNextTurn(null)
      .then((next) => !cancelled && applyTurn(next))
      .catch(() => !cancelled && setStatus('error'))
    return () => {
      cancelled = true
    }
  }, [applyTurn])

  const loadTurn = (afterTurnId) => {
    setStatus('loading')
    fetchTurn(afterTurnId)
  }

  const locked = result?.is_correct === true
  const placedIds = new Set(slots.filter(Boolean).map((tile) => tile.id))
  const allFilled = slots.length > 0 && slots.every(Boolean)

  const placeTile = (tile) => {
    if (locked) return
    const emptyIndex = slots.indexOf(null)
    if (emptyIndex === -1) return
    setResult(null)
    setSlots((prev) => prev.map((s, i) => (i === emptyIndex ? tile : s)))
  }

  const removeTile = (index) => {
    if (locked) return
    setResult(null)
    setSlots((prev) => prev.map((s, i) => (i === index ? null : s)))
  }

  const clearSlots = () => {
    setResult(null)
    setSlots((prev) => prev.map(() => null))
  }

  const checkAnswer = async () => {
    const response = await submitAnswer({
      turn_id: turn.turn_id,
      placed_tile_ids: slots.map((tile) => tile.id),
      answer: slots.map((tile) => tile.text).join(''),
    })
    setResult(response)
    if (response.is_correct) setStars((s) => s + response.stars_earned)
  }

  const restart = () => {
    setStars(0)
    loadTurn(null)
  }

  if (status === 'loading') {
    return <main className="board board--center">{t.loading}</main>
  }

  if (status === 'error') {
    return (
      <main className="board board--center">
        <p>{t.loadError}</p>
        <button type="button" className="action action--primary" onClick={() => loadTurn(turn?.turn_id ?? null)}>
          {t.retry}
        </button>
      </main>
    )
  }

  const finished = locked && !result.has_next_turn

  return (
    <main className="board">
      <header className="board__header">
        <span className="board__progress">
          {t.progress(turn.progress.current, turn.progress.total)}
        </span>
        <span className="board__stars" aria-label={t.stars(stars)}>
          <StarIcon /> {stars}
        </span>
      </header>

      <p className="board__instruction">{t.instruction}</p>

      <Picture className="board__picture" name={turn.picture} label={t.pictureLabel} />

      <section className="board__slots" aria-label={t.slotsLabel}>
        {slots.map((tile, i) => (
          <Slot key={i} index={i} tile={tile} onRemove={removeTile} locked={locked} />
        ))}
      </section>

      <div className="board__feedback">
        {result && (
          <FeedbackBanner tone={result.is_correct ? 'correct' : 'incorrect'}>
            {finished ? t.finished : result.is_correct ? t.correct : t.incorrect}
          </FeedbackBanner>
        )}
      </div>

      <section className="board__tray" aria-label={t.trayLabel}>
        {turn.tiles.map((tile) =>
          placedIds.has(tile.id) ? (
            <div key={tile.id} className="board__tray-gap" aria-hidden="true" />
          ) : (
            <Tile
              key={tile.id}
              text={tile.text}
              onClick={() => placeTile(tile)}
              ariaLabel={t.availableTile(tile.text)}
              disabled={locked || allFilled}
            />
          ),
        )}
      </section>

      <footer className="board__actions">
        {!locked && (
          <>
            <button
              type="button"
              className="action"
              onClick={clearSlots}
              disabled={placedIds.size === 0}
            >
              {t.clear}
            </button>
            <button
              type="button"
              className="action action--primary"
              onClick={checkAnswer}
              disabled={!allFilled}
            >
              {t.check}
            </button>
          </>
        )}
        {locked && !finished && (
          <button type="button" className="action action--primary" onClick={() => loadTurn(turn.turn_id)}>
            {t.next}
          </button>
        )}
        {finished && (
          <button type="button" className="action action--primary" onClick={restart}>
            {t.restart}
          </button>
        )}
      </footer>
    </main>
  )
}
