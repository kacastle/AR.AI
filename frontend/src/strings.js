// All user-facing UI text (Filipino). Feedback lines come from the API.
export const t = {
  loading: 'Sandali lang...',
  loadError: 'May problema. Subukan muli.',
  retry: 'Subukan muli',
  turnLabel: (n) => `Tanong ${n}`,
  learnerTurn: (name) => `Ikaw na, ${name}!`,
  listen: 'Pakinggan',
  instructions: {
    dictation_letters: 'Pakinggan ang salita. Buuin gamit ang mga titik.',
    dictation_syllables: 'Pakinggan ang salita. Buuin gamit ang mga pantig.',
    missing_letter: 'Pakinggan ang salita. Anong titik ang kulang?',
    sentence_builder: 'Pakinggan. Ayusin ang mga salita.',
  },
  modelLabel: 'Tingnan:',
  slotsLabel: 'Mga kahon para sa sagot',
  trayLabel: 'Mga tile na pagpipilian',
  emptySlot: (n) => `Bakanteng kahon ${n}`,
  fixedTile: (text, n) => `${text}, nakalagay na sa kahon ${n}`,
  placedTile: (text, n) => `${text}, nasa kahon ${n}. Pindutin para alisin.`,
  availableTile: (text) => `${text}. Pindutin para ilagay.`,
  clear: 'Burahin',
  check: 'Suriin',
  next: 'Susunod',
  // Generic fallback from CLAUDE.md, used while the API sends no feedback for wrong attempts.
  tryAgain: (name) => `Subukan natin ulit, ${name}!`,
  overlay: {
    title: 'Malapit na!',
    hints: {
      replay_by_syllable: 'Pakinggan ulit ang bawat pantig.',
      highlight_slot: 'Tingnan ang kahong may ilaw.',
      first_tile: 'Magsimula tayo sa unang kahon.',
    },
    retry: 'Subukan ulit',
    listenAgain: 'Pakinggan ulit',
    showAnswer: 'Ipakita ang sagot',
  },
  turnSwitch: {
    start: 'Magsimula',
    avatar: (name) => `Larawan ni ${name}`,
  },
}
