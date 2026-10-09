import Tile from './Tile.jsx'
import { t } from '../strings.js'
import './Slot.css'

export default function Slot({ index, tile, onRemove, locked }) {
  const n = index + 1
  if (!tile) {
    return (
      <div className="slot slot--empty" role="img" aria-label={t.emptySlot(n)} />
    )
  }
  return (
    <div className="slot">
      <Tile
        text={tile.text}
        variant="placed"
        onClick={() => onRemove(index)}
        ariaLabel={t.placedTile(tile.text, n)}
        disabled={locked}
      />
    </div>
  )
}
