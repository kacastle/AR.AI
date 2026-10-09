import { useSyncExternalStore } from 'react'

// Small on/off settings kept in localStorage and shared across components.
function createToggle(key, onChange = () => {}) {
  let value = localStorage.getItem(key) === '1'
  const listeners = new Set()
  onChange(value)
  return {
    get: () => value,
    set(next) {
      value = next
      localStorage.setItem(key, next ? '1' : '0')
      onChange(next)
      listeners.forEach((callback) => callback())
    },
    subscribe(callback) {
      listeners.add(callback)
      return () => listeners.delete(callback)
    },
  }
}

export const sfxMuted = createToggle('rtph.sfx_muted')

export const highContrast = createToggle('rtph.high_contrast', (on) => {
  document.documentElement.dataset.contrast = on ? 'high' : 'normal'
})

export function useToggle(toggle) {
  return useSyncExternalStore(toggle.subscribe, toggle.get)
}
