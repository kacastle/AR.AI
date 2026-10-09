import { useState } from 'react'
import Confetti from '../components/Confetti.jsx'
import { playChime, playPop } from '../sfx.js'
import { useAudio } from '../hooks/useAudio.js'
import { t } from '../strings.js'
import './LessonScreen.css'

const ICONS = { visual: '👀', steps: '🪜', story: '📖', letters: '🔤' }

// Light up the skill's words inside a sentence.
function Sentence({ text, words }) {
  const set = new Set(words.map((w) => w.toLowerCase()))
  return (
    <p className="lesson__sentence pop-in">
      {text.split(/(\s+)/).map((part, i) => {
        const bare = part.replace(/[.,!?"“”]/g, '').toLowerCase()
        return set.has(bare) ? (
          <mark key={i} className="lesson__mark">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      })}
    </p>
  )
}

function Visual({ lesson }) {
  const { example } = lesson
  return (
    <>
      <div className="lesson__tiles" aria-label={example.text}>
        {example.tiles.map((tile, i) => (
          <span
            key={i}
            className={`tile lesson__tile${example.highlight.includes(i) ? ' lesson__tile--lit' : ''}`}
            style={{ animationDelay: `${i * 180}ms` }}
          >
            {tile}
          </span>
        ))}
      </div>
      {example.syllables.length > 1 && (
        <div className="lesson__syllables">
          {example.syllables.map((s, i) => (
            <span key={i} className={`lesson__syllable lesson__syllable--${i % 4}`} style={{ animationDelay: `${600 + i * 250}ms` }}>
              {s}
            </span>
          ))}
        </div>
      )}
      {lesson.more_words.length > 0 && (
        <ul className="lesson__more">
          {lesson.more_words.map((w) => (
            <li key={w.text} className="pop-in">
              <strong>{w.text}</strong> <span>{w.syllables.join(' · ')}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function Steps({ lesson, step }) {
  const shown = lesson.steps.slice(0, step + 1)
  return (
    <div className="lesson__steps">
      {shown.map((s, i) => (
        <div key={i} className={`lesson__step pop-in${i === shown.length - 1 ? ' lesson__step--now' : ''}`}>
          {s}
        </div>
      ))}
    </div>
  )
}

function Story({ lesson, step }) {
  const { sentences, words } = lesson.story
  return (
    <div className="lesson__story">
      {sentences.slice(0, step + 1).map((s, i) => (
        <Sentence key={i} text={s} words={words} />
      ))}
    </div>
  )
}

// One card per letter (vowels first): tap the letter to hear its sound, tap the word to hear the word.
function Letters({ lesson, step, play }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, justifyContent: 'center' }}>
      {lesson.letters.slice(0, step + 1).map((card, i) => (
        <div
          key={card.letter}
          className="pop-in"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
            padding: 16,
            minWidth: 120,
            borderRadius: 20,
            background: i === step ? '#FFF4D6' : '#fff',
            border: `3px solid ${i === step ? '#F28C28' : '#E5E7EB'}`,
          }}
        >
          <button
            type="button"
            onClick={() => play(card.audio)}
            aria-label={card.letter}
            style={{
              width: 96,
              height: 96,
              borderRadius: 20,
              border: 'none',
              borderBottom: '6px solid #D9822B',
              background: 'linear-gradient(180deg, #FFD36B, #FFB23F)',
              fontFamily: 'inherit',
              fontSize: 56,
              fontWeight: 800,
              color: '#4A2C00',
              cursor: 'pointer',
            }}
          >
            {card.letter}
          </button>
          {card.word && (
            <button
              type="button"
              onClick={() => card.word_audio && play(card.word_audio)}
              style={{ border: 'none', background: 'none', fontFamily: 'inherit', fontSize: 24, cursor: 'pointer' }}
            >
              <strong style={{ color: '#C2410C' }}>{card.word.slice(0, card.letter.length)}</strong>
              {card.word.slice(card.letter.length)}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

// Teach first: shown before the tile item when the learner meets a new skill, or (another style) when stuck.
export default function LessonScreen({ lesson, childName, onDone }) {
  const [step, setStep] = useState(0)
  const speaker = useAudio()
  const parts =
    lesson.style === 'steps'
      ? lesson.steps.length
      : lesson.style === 'story'
        ? lesson.story.sentences.length
        : lesson.style === 'letters'
          ? lesson.letters.length
          : 1
  const [done, setDone] = useState(parts <= 1)

  const next = () => {
    if (step + 1 < parts) {
      setStep(step + 1)
      playPop()
      if (lesson.style === 'letters') speaker.play(lesson.letters[step + 1].audio)
      if (step + 2 >= parts) {
        setDone(true)
        playChime()
      }
    }
  }

  return (
    <main className={`screen lesson lesson--${lesson.style} slide-in`}>
      <p className="board__tutor-note">{t.tutorNotes.lesson(lesson.style, lesson.skill_name_en, lesson.reason)}</p>
      {lesson.reason === 'reteach' && <p className="lesson__again pop-in">{t.tryAgain(childName)}</p>}
      <h1 className="screen__title lesson__title">
        <span className="lesson__icon" aria-hidden="true">
          {ICONS[lesson.style]}
        </span>{' '}
        {lesson.skill_name_fil}
      </h1>

      <section className="lesson__stage">
        {lesson.style === 'visual' && <Visual lesson={lesson} />}
        {lesson.style === 'steps' && <Steps lesson={lesson} step={step} />}
        {lesson.style === 'story' && <Story lesson={lesson} step={step} />}
        {lesson.style === 'letters' && <Letters lesson={lesson} step={step} play={speaker.play} />}
      </section>

      <div className="lesson__dots" aria-hidden="true">
        {Array.from({ length: parts }, (_, i) => (
          <span key={i} className={`lesson__dot${i <= step ? ' lesson__dot--on' : ''}`} />
        ))}
      </div>

      <footer className="screen__actions">
        {!done ? (
          <button type="button" className="action action--primary action--glow" onClick={next}>
            {t.next}
          </button>
        ) : (
          <button type="button" className="action action--primary action--glow" onClick={onDone}>
            {t.lesson.yourTurn}
          </button>
        )}
      </footer>
      {done && parts > 1 && <Confetti count={24} />}
    </main>
  )
}
