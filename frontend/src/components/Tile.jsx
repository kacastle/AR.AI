import './Tile.css'

export default function Tile({ text, onClick, ariaLabel, variant = 'tray', disabled = false }) {
  return (
    <button
      type="button"
      className={`tile tile--${variant}`}
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled}
    >
      {text.toLowerCase()}
    </button>
  )
}
