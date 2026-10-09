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
  screens/      Full-page screens (TutorLogin, GroupSetup, ReadAlong, TurnSwitch, TileBoard,
                StoryQuestion, TutorSummary)
  components/   Reusable UI (Tile, Slot, FeedbackBanner, FeedbackOverlay, LearnerPicture, TutorBar)
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

## Session flow (App.jsx)

Login (any PIN, demo stub) → Group setup (attendance; `present` keeps group order) → Read-along
(`read_along_story_id`) → tiles phase → stories phase → Tutor summary. Each phase calls
`POST /api/sessions/{id}/phase`; the tutor bar shows time left from `ends_at` and has "Laktawan" to skip
ahead for a fast demo. The tiles phase ends at the first finished turn after `ends_at`.

Read-along highlights words using `words[].start_ms/end_ms`; it follows the story audio when it plays,
otherwise a timer on the same timings. Tap a word to hear it; "Muling Pakinggan" repeats the paragraph.

Story questions are **not in API_CONTRACT.md yet**. `getStoryTurn()` / `submitStoryAnswer()` in the mock
are a proposal using content.json `stories[].questions` (one question per turn, learners in turn order;
a second wrong answer shows the answer). Question audio uses `/api/audio/{question_id}.wav`, which is
also not a contract key yet.

## Mock or real backend

All screens call `src/api.js`. `.env` sets the mode:

```
VITE_USE_MOCK=true                        # default: offline demo data (src/mocks/api.js)
VITE_API_BASE_URL=http://localhost:8000   # used when VITE_USE_MOCK=false
```

To use the real backend without editing `.env`: `VITE_USE_MOCK=false npm run dev` (or put the line in
`.env.local`, which git ignores). Start the backend first:
`uvicorn backend.main:app --reload --reload-dir backend --port 8000` (add `DEMO_FAST=1` for 1-minute phases).

- Real mode creates the demo group (Teacher Liza: Ana, Ben, Mila) with `POST /api/groups` once and keeps
  its id in `localStorage` (`rtph.group_id`).
- Audio paths from the API (`/api/audio/...`) are prefixed with `VITE_API_BASE_URL`.
- If the backend can't be reached before a session starts, the app switches to the demo data and the
  corner note says "Hindi maabot ang server. Demo na datos muna." After a real session has started,
  errors show on the screen instead, so real and demo data never mix.
- The dev server must run on port 5173: the backend's CORS only allows `http://localhost:5173`.
  A blocked CORS request looks the same as an unreachable server, so it also falls back to demo data.
- Story questions always run locally (no endpoint in `API_CONTRACT.md` yet).
