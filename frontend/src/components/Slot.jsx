import Tile from './Tile.jsx'
import { t } from '../strings.js'
import './Slot.css'

export default function Slot({ index, slot, onRemove, locked, highlighted, keepCase }) {
  const n = index + 1
  const className = `slot${highlighted ? ' slot--highlight' : ''}`
  if (!slot) {
    return (
      <div className={`${className} slot--empty`} role="img" aria-label={t.emptySlot(n)} />
    )
  }
  return (
    <div className={className}>
      <Tile
        text={slot.text}
        variant={slot.fixed ? 'fixed' : 'placed'}
        onClick={() => onRemove(index)}
        ariaLabel={slot.fixed ? t.fixedTile(slot.text, n) : t.placedTile(slot.text, n)}
        disabled={locked || slot.fixed}
        keepCase={keepCase}
      />
    </div>
  )
}
