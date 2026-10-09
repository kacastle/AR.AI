# Reading Tutor PH (frontend)

Offline React + Vite frontend. Plain CSS only (no Tailwind). No network requests at runtime.

## Run

```bash
npm install
npm run dev      # development
npm run build    # production build in dist/
npm run preview  # serve the build
```

## Structure

```
src/
  screens/      Full-page screens (TileBoardScreen, TurnSwitchScreen)
  components/   Reusable UI (Tile, Slot, FeedbackBanner, FeedbackOverlay)
  mocks/api.js  Offline mock of GET /api/sessions/{id}/next and POST /api/sessions/{id}/answer,
                following backend/API_CONTRACT.md (hint ladder, prefill, feedback lines from content/rules.json)
  strings.js    All UI text (Filipino). Feedback lines come from the API.
  assets/fonts/ Andika font (SIL OFL 1.1), bundled locally
```

## Tile board UI rules

- Tiles are at least 64px (`--tile-size: 72px` in `src/index.css`).
- Word text is at least 32px (`--word-size: 40px`).
- Tile text is lowercase (`toLowerCase()` + `text-transform: lowercase`), except `sentence_builder`
  word tiles, which keep their capital letters and punctuation because the answer checks them.
- Tap a tile in the tray to put it in the first empty slot. Tap a placed tile to send it back.
- `prefill` entries are fixed tiles. `support_level: "show"` (and `next_action: "show_answer"`) shows the
  answer as a model and the learner rebuilds it.
- Hints: `highlight_slot` / `first_tile` outline a box; `replay_by_syllable` plays `hint.audio`.
- `ng` is one tile.

## Screens and feedback

- `TurnSwitchScreen` shows a big avatar, "Ikaw na, [Name]!" and "Magsimula" whenever `child_id` changes.
- A wrong answer shakes the tiles, then `FeedbackOverlay` pops up. It shows the API's `feedback` when sent,
  otherwise a hint line for `hint.kind`. On `next_action: "show_answer"` its "Ipakita ang sagot" button
  shows the answer and the learner rebuilds it.
- Buttons and tiles grow on hover (`scale(1.08)`) and shrink when pressed (`scale(0.95)`); "Susunod" glows.
  Animations are cut short under `prefers-reduced-motion`.
