import './Tile.css'

export default function Tile({
  text,
  onClick,
  ariaLabel,
  variant = 'tray',
  disabled = false,
  keepCase = false,
}) {
  return (
    <button
      type="button"
      className={`tile tile--${variant}${keepCase ? ' tile--keep-case' : ''}`}
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled}
    >
      {keepCase ? text : text.toLowerCase()}
    </button>
  )
}
