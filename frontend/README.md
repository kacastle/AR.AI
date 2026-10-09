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
  screens/      Full-page screens (TileBoardScreen)
  components/   Reusable UI (Tile, Slot, FeedbackBanner)
  mocks/api.js  Offline mock API: getNextTurn(), submitAnswer(), sample "Next turn" / "Answer" payloads
  strings.js    All UI text (Filipino)
  assets/fonts/ Andika font (SIL OFL 1.1), bundled locally
```

## Tile board UI rules

- Tiles are at least 64px (`--tile-size: 72px` in `src/index.css`).
- Word text is at least 32px (`--word-size: 40px`).
- Tile text is always lowercase (`toLowerCase()` + `text-transform: lowercase`).
- Tap a tile in the tray to put it in the first empty slot. Tap a placed tile to send it back.
