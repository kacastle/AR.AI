import { useCallback, useEffect, useRef, useState } from 'react'

// Plays one clip at a time and reports `speaking` so the UI can pulse the speaker button.
// If the clip can't load (offline mock, audio not generated yet) it still "speaks" for
// `fallbackMs` so the learner sees the same cue.
export function useAudio() {
  const [speaking, setSpeaking] = useState(false)
  const current = useRef(null)

  const release = (entry) => {
    entry.audio.pause()
    clearTimeout(entry.timer)
  }

  const stop = useCallback(() => {
    if (current.current) release(current.current)
    current.current = null
    setSpeaking(false)
  }, [])

  const play = useCallback(
    (url, fallbackMs = 1600) => {
      stop()
      if (!url) return
      const entry = { audio: new Audio(url), timer: null }
      current.current = entry
      setSpeaking(true)
      const done = () => {
        if (current.current !== entry) return
        current.current = null
        setSpeaking(false)
      }
      const fallback = () => {
        clearTimeout(entry.timer)
        entry.timer = setTimeout(done, fallbackMs)
      }
      entry.audio.addEventListener('ended', done)
      entry.audio.addEventListener('error', fallback)
      entry.audio.play().catch(fallback)
    },
    [stop],
  )

  useEffect(
    () => () => {
      if (current.current) release(current.current)
    },
    [],
  )

  return { speaking, play, stop }
}
