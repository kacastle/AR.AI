import logo from '../assets/logo-trim.png'
import { t } from '../strings.js'
import './LoadingOverlay.css'

// Full-screen loader: the AR.AI logo with its open book glowing and a page flipping.
// Fades in after a short delay so quick loads don't flash.
export default function LoadingOverlay({ label = t.loading }) {
  const mask = `url(${logo})`
  return (
    <div className="loading" role="status" aria-live="polite">
      <div className="loading__plate">
        <div className="loading__logo">
          <img src={logo} alt="" />
          <span className="loading__page" aria-hidden="true" />
          <span className="loading__shine" style={{ WebkitMaskImage: mask, maskImage: mask }} aria-hidden="true" />
        </div>
      </div>
      <p className="loading__label">{label}</p>
    </div>
  )
}
