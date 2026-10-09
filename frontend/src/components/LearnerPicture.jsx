const INK = '#2b2b3a'

const BACKGROUNDS = { cat: '#ffd6a8', dog: '#bfe3ff', star: '#dcc8ff' }

const PICTURES = {
  cat: (
    <g>
      <path d="M50 86 L60 30 L94 62Z" fill="#f2994a" />
      <path d="M150 86 L140 30 L106 62Z" fill="#f2994a" />
      <circle cx="100" cy="112" r="58" fill="#f2994a" />
      <circle cx="78" cy="104" r="8" fill={INK} />
      <circle cx="122" cy="104" r="8" fill={INK} />
      <path d="M92 122 L108 122 L100 131Z" fill="#ff7a8a" />
      <path d="M100 131 Q92 144 82 138 M100 131 Q108 144 118 138" stroke={INK} strokeWidth="4" fill="none" strokeLinecap="round" />
      <path d="M38 118 L68 122 M38 134 L68 130 M162 118 L132 122 M162 134 L132 130" stroke={INK} strokeWidth="3" strokeLinecap="round" />
    </g>
  ),
  dog: (
    <g>
      <circle cx="100" cy="112" r="58" fill="#c68b59" />
      <ellipse cx="50" cy="100" rx="18" ry="38" fill="#7a4e2d" transform="rotate(18 50 100)" />
      <ellipse cx="150" cy="100" rx="18" ry="38" fill="#7a4e2d" transform="rotate(-18 150 100)" />
      <circle cx="80" cy="102" r="8" fill={INK} />
      <circle cx="120" cy="102" r="8" fill={INK} />
      <ellipse cx="100" cy="124" rx="14" ry="10" fill={INK} />
      <path d="M96 144 Q100 160 104 144Z" fill="#ff7a8a" />
      <path d="M84 140 Q100 152 116 140" stroke={INK} strokeWidth="4" fill="none" strokeLinecap="round" />
    </g>
  ),
  star: (
    <g>
      <path
        d="M100 28 L120 76 L170 78 L131 110 L144 160 L100 132 L56 160 L69 110 L30 78 L80 76Z"
        fill="#ffd84d"
        stroke="#e0a800"
        strokeWidth="5"
        strokeLinejoin="round"
      />
      <circle cx="87" cy="98" r="6" fill={INK} />
      <circle cx="113" cy="98" r="6" fill={INK} />
      <path d="M88 114 Q100 124 112 114" stroke={INK} strokeWidth="4" fill="none" strokeLinecap="round" />
    </g>
  ),
  default: (
    <g>
      <circle cx="100" cy="112" r="62" fill="#ffe2c4" />
      <path d="M38 104 Q44 40 100 40 Q156 40 162 104 Q140 72 100 70 Q60 72 38 104Z" fill="#3b2a20" />
      <circle cx="78" cy="110" r="8" fill={INK} />
      <circle cx="122" cy="110" r="8" fill={INK} />
      <path d="M80 136 Q100 156 120 136" stroke={INK} strokeWidth="6" fill="none" strokeLinecap="round" />
    </g>
  ),
}

// `picture` is the free-form string the API stores per learner (cat, dog, star, ...).
export default function LearnerPicture({ picture, label, className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 200 200"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <circle cx="100" cy="100" r="96" fill={BACKGROUNDS[picture] ?? '#c8f0d2'} />
      {PICTURES[picture] ?? PICTURES.default}
    </svg>
  )
}
