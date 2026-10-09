import { sfxMuted } from './preferences.js'

// Short game sounds made with the Web Audio API (no audio files, works offline).
let context = null

function audioContext() {
  const Context = window.AudioContext || window.webkitAudioContext
  if (!Context) return null
  if (!context) context = new Context()
  if (context.state === 'suspended') context.resume()
  return context
}

function tone(ac, { freq, endFreq = freq, start = 0, duration, type = 'sine', volume = 0.12 }) {
  const t0 = ac.currentTime + start
  const osc = ac.createOscillator()
  const gain = ac.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t0)
  if (endFreq !== freq) osc.frequency.exponentialRampToValueAtTime(endFreq, t0 + duration)
  gain.gain.setValueAtTime(0.0001, t0)
  gain.gain.exponentialRampToValueAtTime(volume, t0 + 0.012)
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + duration)
  osc.connect(gain).connect(ac.destination)
  osc.start(t0)
  osc.stop(t0 + duration + 0.02)
}

function play(build) {
  if (sfxMuted.get()) return
  try {
    const ac = audioContext()
    if (ac) build(ac)
  } catch {
    // No audio device; stay silent.
  }
}

export const playPop = () => play((ac) => tone(ac, { freq: 520, endFreq: 880, duration: 0.09 }))

export const playChime = () =>
  play((ac) =>
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) =>
      tone(ac, { freq, start: i * 0.09, duration: 0.45, type: 'triangle' }),
    ),
  )
