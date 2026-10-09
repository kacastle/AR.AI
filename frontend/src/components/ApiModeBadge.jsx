import { useSyncExternalStore } from 'react'
import { getApiMode, subscribeApiMode } from '../api.js'
import { t } from '../strings.js'
import './ApiModeBadge.css'

// Small corner note so the tutor (and developers) can tell demo data from the real server.
export default function ApiModeBadge() {
  const mode = useSyncExternalStore(subscribeApiMode, getApiMode)
  return (
    <p
      className={`api-mode api-mode--${mode}`}
      aria-live="polite"
      // Demo data must never pass for the real tutor: the fallback is a loud banner, not a corner note.
      style={mode === 'fallback' ? { background: '#B91C1C', color: '#fff', fontWeight: 800, fontSize: 18, padding: '10px 16px' } : undefined}
    >
      {t.apiMode[mode]}
    </p>
  )
}
