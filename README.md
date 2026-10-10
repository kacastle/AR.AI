# AR.AI — ReadingTutor PH

An adaptive tutor's assistant for children learning to read Filipino (DepEd ARAL-Reading, Key Stage 1).
One tutor, one laptop, up to 3 learners, a session of 60 minutes or less. It runs **fully offline**:
a local language model writes stories and practice words in the background, while fixed rules decide
what each child practises next, so no turn ever waits for the model.

## For the judges: run it in 4 steps

Tested on Windows 11 (PowerShell), 16 GB RAM, CPU only. macOS/Linux work the same way (differences noted).
You need **Python 3.10+**, **Node.js 20+**, **Git** and **[Ollama](https://ollama.com/download)**.
Everything below runs from the repo folder.

### 1. Get the code and install
```powershell
git clone https://github.com/kacastle/AR.AI.git
cd AR.AI
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cd frontend; npm ci; cd ..
```

### 2. Get the local model (one time, 6.6 GB)
Start Ollama, then:
```powershell
ollama pull gemma4:e4b
```
Without Ollama the app still works: stories and practice words fall back to the reviewed library and templates.

### 3. Start the app (two terminals)
Terminal 1, the backend:
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --port 8000
```
Terminal 2, the frontend:
```powershell
cd frontend
npm run dev
```
Open **http://localhost:5173**. Any PIN works on the tutor login (demo).

The first start downloads the voice model (k2-fsa/OmniVoice, about 3 GB, one time). To skip it, don't install
`omnivoice`: all word, syllable and library-story audio is already in `audio_cache/`; only new stories written
during a session are then shown as text only.

### 4. Optional: a quick demo
```powershell
python scripts/seed_demo.py --fresh      # 3 fake returning learners with past sessions (progress graph)
$env:DEMO_FAST="1"                       # before starting the backend: 1-minute phases, 20-second items
$env:AUTO_APPROVE="1"                    # demo only: model stories reach learners without tutor approval
```
macOS/Linux: `export DEMO_FAST=1` instead of `$env:DEMO_FAST="1"`.

### Check that everything works
```powershell
python -m pytest                          # all tests (no model needed)
python -m backend.content                 # content check: prints OK
python scripts/simulate.py                # 3 learners through the real API
python scripts/pregen_audio.py --check    # every word and story has audio
```

## What you will see
1. Tutor login, then group setup (pick the learners present).
2. Read-along story with word highlighting.
3. Tile turns: each learner in turn builds the word they hear from letter or syllable tiles. Mistakes get
   Filipino feedback and hints (syllable-by-syllable replay, highlighted box, first tile, then the answer).
4. Story turns: each learner's own story with questions.
5. Tutor summary and a printable practice sheet for home.

## How it is built
- **backend/** — FastAPI + SQLite. Rules engine (mistake classifier, scoring, skill selection, review,
  placement), background model worker, audio. API shapes: `backend/API_CONTRACT.md`.
- **frontend/** — React + Vite. Talks to the backend through Vite's `/api` proxy.
- **content/** — skills, words, stories and rules (`content.json`, `rules.json`), prompts, and the
  recorded syllables (`content/recordings/`).
- **audio_cache/** — every clip the app plays, committed so nothing has to be generated before a demo.
  Words and syllables are a person's recordings; sentences and stories are read by OmniVoice.
- Model: `gemma4:e4b` on Ollama by default (`OLLAMA_MODEL` changes it). Every model output is checked by
  code; a failed output is retried once, then a reviewed template is used.

Learner data stays in the local SQLite file (`data/tutor.db`, never committed). Demo data uses fake names.

## Troubleshooting
- **Red "mock" banner in the app**: the backend is not running on port 8000; start terminal 1.
- **Port already in use**: another backend or frontend is still running; close it, or use
  `uvicorn backend.main:app --port 8001` with `$env:BACKEND_URL="http://127.0.0.1:8001"` before `npm run dev`.
- **Slow first story**: the model and the voice warm up in the background at start; the backend log shows
  `[llm] ... warm-up ... ok` when ready.
- **Fully offline after setup**: `$env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"` before the backend.
