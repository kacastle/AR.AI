import { useSyncExternalStore } from 'react'
import { getApiMode, subscribeApiMode } from '../api.js'
import { t } from '../strings.js'
import './ApiModeBadge.css'

// Small corner note so the tutor (and developers) can tell demo data from the real server.
export default function ApiModeBadge() {
  const mode = useSyncExternalStore(subscribeApiMode, getApiMode)
  return (
    <p className={`api-mode api-mode--${mode}`} aria-live="polite">
      {t.apiMode[mode]}
    </p>
  )
}
