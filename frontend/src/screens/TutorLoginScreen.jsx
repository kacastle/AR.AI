import { useState } from 'react'
import { login } from '../api.js'
import { t } from '../strings.js'
import './TutorLoginScreen.css'

const PIN_LENGTH = 4
const DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9']

export default function TutorLoginScreen({ onDone }) {
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  const addDigit = (d) => {
    setError(false)
    setPin((p) => (p.length < PIN_LENGTH ? p + d : p))
  }

  const removeDigit = () => setPin((p) => p.slice(0, -1))

  const submit = async () => {
    setBusy(true)
    try {
      const response = await login({ pin })
      if (response.ok) return onDone()
      setError(true)
      setPin('')
    } catch {
      setError(true)
    }
    setBusy(false)
  }

  const digitKey = (d) => (
    <button key={d} type="button" className="pin__key" onClick={() => addDigit(d)} aria-label={t.login.digit(d)}>
      {d}
    </button>
  )

  return (
    <main className="screen login">
      <h1 className="screen__title">{t.login.title}</h1>
      <p className="screen__subtitle">{t.login.prompt}</p>
      <div className="pin__dots" role="img" aria-label={t.login.filled(pin.length, PIN_LENGTH)}>
        {Array.from({ length: PIN_LENGTH }, (_, i) => (
          <span key={i} className={`pin__dot${i < pin.length ? ' pin__dot--filled' : ''}`} />
        ))}
      </div>
      <p className={`login__note${error ? ' login__note--error' : ''}`} role="status">
        {error ? t.login.error : t.login.demoNote}
      </p>
      <div className="pin__pad">
        {DIGITS.map(digitKey)}
        <button
          type="button"
          className="pin__key pin__key--small"
          onClick={removeDigit}
          disabled={!pin}
          aria-label={t.login.deleteLabel}
        >
          {t.login.delete}
        </button>
        {digitKey('0')}
        <button
          type="button"
          className="pin__key pin__key--small pin__key--enter"
          onClick={submit}
          disabled={pin.length < PIN_LENGTH || busy}
        >
          {t.login.enter}
        </button>
      </div>
    </main>
  )
}
