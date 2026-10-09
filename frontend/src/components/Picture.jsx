import bata from '../assets/pictures/bata.svg'
import aso from '../assets/pictures/aso.svg'
import bahay from '../assets/pictures/bahay.svg'

const pictures = { bata, aso, bahay }

export default function Picture({ name, label, className }) {
  const src = pictures[name]
  return (
    <div className={className} role="img" aria-label={label}>
      {src && <img src={src} alt="" width="120" height="120" />}
    </div>
  )
}
