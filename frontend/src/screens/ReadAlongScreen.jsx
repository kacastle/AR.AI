import { useEffect, useRef, useState } from 'react'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import SpeakerIcon from '../components/SpeakerIcon.jsx'
import { getStory } from '../api.js'
import { t } from '../strings.js'
import './ReadAlongScreen.css'

// The API lists `words` for the whole story; split them back into paragraphs.
function wordRanges(paragraphs) {
  let start = 0
  return paragraphs.map((p) => {
    const count = p.split(/\s+/).filter(Boolean).length
    const range = [start, start + count]
    start += count
    return range
  })
}

function stopPlayback(playback) {
  cancelAnimationFrame(playback.raf)
  playback.audio?.pause()
  playback.audio = null
}

export default function ReadAlongScreen({ storyId, onDone }) {
  const [story, setStory] = useState(null)
  const [error, setError] = useState(false)
  const [paragraph, setParagraph] = useState(0)
  const [active, setActive] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const [heard, setHeard] = useState(false)
  const playback = useRef({ raf: 0, audio: null })

  useEffect(() => {
    let cancelled = false
    const current = playback.current
    getStory(storyId)
      .then((s) => !cancelled && setStory(s))
      .catch(() => !cancelled && setError(true))
    return () => {
      cancelled = true
      stopPlayback(current)
    }
  }, [storyId])

  if (error) return <main className="screen screen--center">{t.loadError}</main>
  if (!story) return <LoadingOverlay label={t.loadingStory} />

  const ranges = wordRanges(story.paragraphs)
  const [from, to] = ranges[paragraph]
  const last = paragraph === story.paragraphs.length - 1

  // Highlights words from start_ms/end_ms. Follows the audio clock when the story audio
  // plays; otherwise (no audio yet, offline) a timer runs on the same timings.
  const play = (first, end, wholeParagraph) => {
    stopPlayback(playback.current)
    const { words } = story
    const startMs = words[first].start_ms
    const endMs = words[end - 1].end_ms
    const audio = new Audio(story.audio_url)
    audio.currentTime = startMs / 1000
    audio.play().catch(() => {})
    playback.current.audio = audio
    const t0 = performance.now()
    setPlaying(true)

    const tick = () => {
      const audioClock = !audio.paused && audio.readyState >= 2
      const now = audioClock ? audio.currentTime * 1000 : startMs + performance.now() - t0
      if (now >= endMs) {
        stopPlayback(playback.current)
        setActive(-1)
        setPlaying(false)
        if (wholeParagraph) setHeard(true)
        return
      }
      let index = first
      while (index + 1 < end && words[index + 1].start_ms <= now) index += 1
      setActive(index)
      playback.current.raf = requestAnimationFrame(tick)
    }
    tick()
  }

  const goNext = () => {
    stopPlayback(playback.current)
    setActive(-1)
    setPlaying(false)
    if (last) return onDone()
    setParagraph((p) => p + 1)
    setHeard(false)
  }

  return (
    <main className="screen read">
      <p className="screen__subtitle">{t.readAlong.heading}</p>
      <h1 className="screen__title">{story.title}</h1>
      <div className="read__dots" role="img" aria-label={t.readAlong.paragraphOf(paragraph + 1, ranges.length)}>
        {ranges.map((_, i) => (
          <span key={i} className={`read__dot${i <= paragraph ? ' read__dot--done' : ''}`} />
        ))}
      </div>

      <p className="read__paragraph">
        {story.words.slice(from, to).map((word, k) => {
          const i = from + k
          return (
            <button
              key={i}
              type="button"
              className={`read__word${i === active ? ' read__word--active' : ''}`}
              onClick={() => play(i, i + 1, false)}
            >
              {word.text}
            </button>
          )
        })}
      </p>

      <p className="read__echo" aria-live="polite">
        {heard ? t.readAlong.echo : t.readAlong.instruction}
      </p>

      <footer className="screen__actions">
        <button
          type="button"
          className={`action read__listen${playing ? ' action--speaking' : ''}`}
          onClick={() => play(from, to, true)}
        >
          <SpeakerIcon />
          {heard ? t.readAlong.repeat : t.listen}
        </button>
        <button
          type="button"
          className={`action action--primary${heard ? ' action--glow' : ''}`}
          onClick={goNext}
        >
          {last ? t.readAlong.done : t.readAlong.nextParagraph}
        </button>
      </footer>
    </main>
  )
}
