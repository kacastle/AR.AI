Project: ReadingTutor PH. Offline tutor's assistant for DepEd ARAL-Reading, Key Stage 1, Filipino. One tutor, one laptop, 3 learners, 60 minutes or less. Fully offline.

## Who owns what
I am Person 2. I own backend/, scripts/, tests/. Do not edit frontend/ (Person 1) or content/ (Person 3, Kiefer). content/ files are read-only inputs and may be replaced by newer versions at any time (content v0.2 is in content/ now).
Exception (2026-10-10, feedback round 2): Kiefer approved one round of edits across all folders (branch feedback-round-2).

## Stack
Python FastAPI + Pydantic, SQLite, Ollama with JSON output, OmniVoice k2-fsa/OmniVoice (language fil, default voice) for text to speech. Windows with PowerShell, venv in .venv.
Installed in .venv: fastapi, uvicorn, transformers, torch (CPU build), torchaudio (CPU build), omnivoice, pytest (listed in requirements.txt; torch/torchaudio from the CPU index). Ask before adding anything else, and add it to requirements.txt.
Model name is NOT hardcoded. Read it from the environment variable OLLAMA_MODEL (default gemma4:e4b, the model content/test_prompts.py v0.3 is tuned for). Never write "3B" in code, docs or comments; use the real model name.

## Principles
- Rules decide what to teach. The model only writes stories, practice words, feedback wording and summaries inside limits.
- Code checks every model output. Fixed templates are the fallback.
- No turn waits for the model. Every turn returns in under 1 second.
- Model work runs in the background (thread or queue), never inside /next or /answer.

## Hard rules
- No network calls except localhost, unless LLM_PROVIDER is auto or cloud (Gemini, story jobs only for auto; the learner's name is replaced by a placeholder before the call). No new dependencies without asking.
- Do not rename JSON fields or ids from content/content.json and content/rules.json.
- ng is one tile.
- Learner data stays in the local SQLite file. Never commit *.db or real child data. Use fake names in seed data. audio_cache/ IS committed (generated clips take about 2 hours to remake): after pregen_audio.py remakes clips, commit audio_cache/ too, including _settings.json; audio_cache/try_* (the OmniVoice listening-test clips) is committed too, for the team to compare. audio_cache/ts_* and gs_* (session stories, they say a learner's name) are gitignored and never committed.
- Never invent Tagalog text. Use only text from content files, test_prompts.py prompts, or templates I paste. If a template is missing, use the generic fallback below and tell me.

## Layout and how to run
Everything runs from the repo root (C:\Users\admin\reading-tutor) with the venv active.
- Judges and new machines: README.md has the step-by-step setup and run instructions (install, ollama pull, two terminals, demo options, checks). Keep it in sync when a run command changes.
- backend/: main.py (routes), schemas.py (API shapes), db.py, content.py (loads and checks content/), records.py (skill states and learner info from the database), summary.py (tutor summary), API_CONTRACT.md, engine/ (classifier, scoring, selector, rotation, review, state, feedback), llm/ (harness loads content/test_prompts.py; client, prompts, checks, fallbacks, jobs; worker = background thread), tts/ (audio plan, clip building; omni.py = OmniVoice speaker). Each folder has an __init__.py.
- tests/ (repo root): API, content, audio, model-job and testbench tests (test_api.py, test_content.py, test_audio.py, test_llm.py, test_testbench.py); tests/conftest.py sets LLM_WORKER=0. The prompt test harness is content/test_prompts.py. backend/tests/: engine unit tests (classifier, scoring, selector, rotation, review) with a shared conftest.py. `python -m pytest` runs both.
- scripts/: test_ollama.py, simulate.py (3-learner session through the real API), pregen_audio.py, testbench.py + testbench/ (real frontend against the real backend), pull_models.sh. Still to come: seed_demo.py.
- content/ (Person 3), frontend/ (Person 1).
- Imports: package style only, for example `from backend.db import ...`. Never `from db import ...`.
- Server: `uvicorn backend.main:app --reload --reload-dir backend --port 8000`
- Tests: `python -m pytest`
- Content check (for Person 3): `python -m backend.content` prints OK or a numbered list of problems.
- Simulation: `python scripts/simulate.py`
- Scripts: `python scripts/pregen_audio.py` (`--force` remakes all, `--check` only checks, `--short` remakes only out-of-date words, syllables and slow hints; each clip's text and voice settings are stamped in audio_cache/_settings.json). A full run takes about an hour on the CPU (about 8 s per clip, about 65 s per story).
- Testbench: `python scripts/testbench.py` then http://localhost:5173 (first time: `cd frontend; npm ci`)
- Model worker: on by default in the server; warms up the model and the voice at startup; logs the seconds of every model and voice call ("[llm] HH:MM:SS ... 12.3 s, ok"). `$env:LLM_WORKER="0"` turns it off. Needs Ollama running with OLLAMA_MODEL pulled.
- Demo auto-approve: `$env:AUTO_APPROVE="1"` approves checked model stories and practice words as soon as they are saved (backend/llm/jobs.py `_save`), so they reach learners without POST /api/approvals. Demos only, never with real children.
- Demo run: `python scripts/demo_session.py` (DEMO_FAST session with 3 fake learners, real model; prints every model call time).
- Database: data/tutor.db (gitignored). `DB_PATH` overrides it. New columns are added automatically on startup.
- Demo timing: `$env:DEMO_FAST="1"` uses rules.json session.demo_fast (1-minute phases, 20-second items).
- Offline mode (PowerShell): `$env:HF_HUB_OFFLINE="1"; $env:TRANSFORMERS_OFFLINE="1"`
- Docs page: http://localhost:8000/docs
- Demo data: `python scripts/seed_demo.py --fresh` (3 fake returning learners, 3 past sessions each, for the progress graph and the "Returning learners" picker).
- Cloud model (optional, local first): `$env:LLM_PROVIDER="auto"; $env:GEMINI_API_KEY="..."` (optional `GEMINI_MODEL`, default gemini-2.5-flash). Story jobs go to Gemini when online; any error or no internet falls back to the local model. Default `local`.
- Frontend: VITE_USE_MOCK=false is the default now (frontend/.env); the mock fallback shows a red banner. Run the backend (`uvicorn backend.main:app --port 8000`) and then `cd frontend; npm run dev`, and open http://localhost:5173: Vite proxies /api to port 8000 (BACKEND_URL overrides). CORS accepts any localhost or 127.0.0.1 port.

## Model prompts and checks
content/test_prompts.py (v0.3; runs on Ollama gemma4:e4b by default) holds the prompt text and the check functions I use to compare models. It reads the content files next to it and writes its results*.csv and stories_for_review*.md files next to itself. Reuse them; do not write a second copy of any prompt or check. If code must move, move it into backend/llm/ and make test_prompts.py import from there.
Story, practice words, feedback and summary prompts come from content/prompts.md. Retry a failed output once, then use the library or template fallback.

## API
POST /api/tutor/login; GET /api/groups/{id}; POST /api/groups; POST /api/sessions; GET /api/stories/{id}; POST /api/sessions/{id}/phase; GET /api/sessions/{id}/next; POST /api/sessions/{id}/answer; GET /api/sessions/{id}/story_turn; POST /api/sessions/{id}/story_answer (each learner's own story quiz; moves children.story_level, queues the next story); GET /api/children/{id}/profile; GET /api/interests; GET /api/sessions/{id}/summary; GET /api/children/{id}/sheet; GET /api/approvals; POST /api/approvals/{id}; GET /api/audio/{key}.wav.
Person 1 builds against these shapes, so never change or rename a field without telling me first. Every shape, with one example response, lives in backend/API_CONTRACT.md. Keep that file in sync with the code. CORS allows http://localhost:5173.

Next turn: child_id, child_name, turn_number, task_type, item (id, prompt_audio, slots, tiles, syllables), support_level, prefill, gap_slot, seconds.
- gap_slot: for missing_letter, the 0-based box the learner fills; null otherwise.
- task_type: dictation_letters, dictation_syllables, missing_letter, sentence_builder (from rules.json selection.task_types_by_category).
- prefill has one entry per slot; "" = empty slot. show = full answer, guide = first tile, alone = all empty; missing_letter = every slot except the gap.
Answer: child_id, item_id, given, hints_used, attempt, time_ms.
- given is the content of all slots, left to right (missing_letter too). attempt starts at 1 per item.
Result: correct, mistake_type, feedback (message_fil, hint_fil), hint (kind, audio, highlight_slot), next_action (retry, show_answer, next), answer.
hint.kind: replay_by_syllable, highlight_slot, first_tile.
Other shapes (keep flat and simple, reuse content.json field names):
- login: body {pin}, returns {ok} (demo stub: any PIN works)
- groups: group with learners (name, picture, profile, interests); profile must be in rules.json placement.profiles; interests optional, up to 3 content.json interest ids
- sessions: body {group_id, present[]}, returns session with read_along_story_id and story_ids {child_id: story id} (approved model story -> filled template -> library story)
- stories: {title, paragraphs, words[{text, start_ms, end_ms}], audio_url} (word timings after pregen_audio.py: exact per sentence, estimated by letter count inside a sentence); approved model stories (gs_ ids) too
- phase: body {phase}, returns {phase, ends_at}
- summary: learners[{child_id, summary, next_focus_skill, next_method}] and group_note (the model's summary once it is ready and current, else the English fallback template from prompts.md section 4)
- sheet: name, date, 5 words with syllables, 1 sentence, home_line_fil
- approvals: waiting model items (story, words); POST body {approve}, returns {ok}

## Engine rules
All numbers are read from content/rules.json. The values below are the current ones.
- Mistake classifier checks in this order: same tiles in a different order = O_ORDER; n and g as two tiles where ng was expected = O_NG; then Levenshtein alignment: vowel for vowel = P_SUB_VOWEL, consonant for consonant = P_SUB_CONS, ng replaced by n = O_NG, one deleted tile at the end = P_OMIT_FINAL, in the middle = P_OMIT_MID, two or more deleted tiles in a row = S_SYLL_MISS, extra tile = P_ADD. With several mistakes return the first from the left. Vowel for consonant (or the other way) goes by the expected tile. (rules.md section 7 puts the ng check first; Person 3 has been told.)
- Score: new = old + 0.3 x (result - old), once per item when it ends. Results: alone 1.0, guide or 1 hint 0.7, shown 0.4, wrong 0.0. Correct at support show, or after 2+ hints, counts as shown (0.4), so mastery needs support alone.
- An item counts as correct (for streaks, "last 3 correct" and rotation) when the first attempt was right.
- Mastered at 0.85 with 8 attempts and last 3 correct. Reteach below 0.60: support resets to show only when a skill falls from practice into reteach. Review after 1, 3, 7, 14 days; a failed review resets the score to 0.70 and support to guide.
- Support: up after 3 correct in a row, down after 2 wrong in a row. 3 wrong in a row: one easy item from a mastered skill (or the current skill at easy difficulty if none is mastered).
- Selection: due review skill first, else the weakest unlocked skill (all prerequisites mastered). Comprehension skills are for the story turn, not tile turns. Task types rotate per skill. Unused items first; when all are used, the one seen longest ago comes back. Items seen in the last session are avoided.
- Difficulty: after 10 items, accuracy above 0.90 = hard (4 distractors, most syllables), below 0.60 = easy (2 distractors, fewest syllables), else normal (3). Words with ng always get n and g as distractors.
- Placement: 2 items per skill in rules.json placement.skills; a skill passes only if both are right. Stop after 2 failed skills in a row. Passed skills start at 0.70 and count as mastered (no review dates). Practice starts at the first failed skill. low_emergent if a skill before sk_cvcv_1 fails, else high_emergent.
- Timers: item_seconds 60 is the limit for an item; slow_seconds 30 triggers the SLOW rule.
- Correction steps: hint 1 replay_by_syllable, hint 2 highlight_slot, hint 3 first_tile, then next_action show_answer so the learner rebuilds it, then next.

## Fixed feedback templates (message_fil / hint_fil)
The code uses rules.json feedback_templates for every code (confirmed): CORRECT (rotates its 3 lines), SHOW_ANSWER and each mistake code, with {name}, {syllables_hyphen}, {syllables_last_caps} and {slots} filled from the item (so the hints below say the current word's syllables). The lines below are the examples for bahay, mesa and sapatos.
- P_OMIT_FINAL: Malapit na, {name}! / Pakinggan ang huling pantig: ba-HAY.
- P_SUB_VOWEL: Magaling ang subok mo! / Pakinggan: me-sa. E ba o I?
- O_NG: Kaya mo ito! / Hanapin ang tile na ng.
- S_SYLL_MISS: Konti na lang! / Pumalakpak tayo: sa-pa-tos. Ilang pantig?
- Correct: Ang galing mo, {name}!
- Generic fallback for any other code (Kiefer must confirm): Subukan natin ulit, {name}!

## Progress
- P2-0 done: FastAPI skeleton, test_ollama.py, test_tts.py (removed with the MMS voice on 2026-10-10).
- P2-1 done: Pydantic shapes, SQLite tables, content loader and checks, every endpoint returns its shape with real content, API_CONTRACT.md.
- P2-3 done: classifier with tests (backend/engine/classifier.py).
- P2-4 done: scoring, selector, rotation, review and placement with tests, wired into /next and /answer; simulate.py shows 3 learners changing skill and support level.
- P2-5 done: classifier and template feedback in /answer, correction steps (attempt 5 ends the item), events.turn_number; gap_slot in /next.
- P2-2 done: pregen_audio.py (sentence by sentence, natural stories with word timings, recording overrides in content/recordings/, remakes clips whose text changed or when backend/tts/omni.py settings change).
- Voice: OmniVoice since 2026-10-10 (backend/tts/omni.py): default voice, language fil, SPEED 0.65 (about 2.6 words per second, a normal talking pace), clips saved at 16 kHz, up to 8 tries when a clip comes back silent. Every clip gets an explicit duration from audio.speech_seconds (letter weights / SPEED, at least MIN_SPEECH_SECONDS 0.5): OmniVoice's own estimate stretched short text (a syllable got 1.3 s) and filled it with mumble. A Whisper check of each word was tried and dropped: about 70 s per clip on this CPU. facebook/mms-tts-tgl was dropped: its letter "a" has the same id as the blank between letters, so short words and syllables lost their "a" ("bahay" sounded like "Dai"). Syllables are recorded by a person (OmniVoice makes a thud for a lone syllable): one 16 kHz file per syllable, content/recordings/syl_{syllable}.wav (RECORDINGS_DIR overrides), used for syl_*, the syllable items y_*, the slow hints and the words (w_*: the word's recorded syllables, whole, with 80 ms pauses, audio.WORD_GAP_MS; a long recording is split with 100 ms margins so p/t/k bursts survive; OmniVoice only if a syllable is missing). OmniVoice still says sentences, stories and feedback lines. `python scripts/recordings.py --list` shows what is missing, `--import FOLDER` converts any WAV; then `python scripts/pregen_audio.py --short`.
- P2-6 done: backend/llm/ client.py (Ollama, localhost only, pauses 30 s after a refused connection), prompts.py and checks.py (thin layers over content/test_prompts.py: no second copy), fallbacks.py (story order from rules.md 9), jobs.py, worker.py (background thread). Stories get audio before they reach /api/approvals and stay hidden until approved; without a voice model (2026-10-10: OmniVoice no longer needed, audio_cache covers words and library stories) a model story is kept as text only ("audio": false) instead of dropped. Retry once on a failed check, never on a missing model. Target words stay optional (Kiefer's v0.3 rules), although the P2-6 spec asked for all of them.
- P2-8 done: warm-up at startup, timed model calls, job priorities (warm-up, template audio, summary, words, stories), stories queued at the end of the session (prompts.md 0), DEMO_FAST tested, scripts/demo_session.py.
- P2-7 done: backend/summary.py (numbers incl. alert, prompt values, template with skill names, current model summary); /summary and /sheet work with Ollama off.
- Testbench: scripts/testbench.py runs the real frontend against the real backend (the frontend's own client, VITE_USE_MOCK=false, through Vite's /api proxy).
- Sign-up and lessons (demo branch): the tutor signs up each learner (name, picture, interests, diagnostic) in the frontend. backend/lessons.py: a lesson (visual, steps or story) before a learner's first item of a skill and, in another style, when a re-teach starts; whether it worked is remembered (rules.json lessons). Story lessons come from the model (prompts.md section 7, job "lesson", queued at session start and when a re-teach starts). LLM_BACKEND=lmstudio runs the model jobs on LM Studio.
- Learner loop (demo branch): backend/adapt.py: diagnostic (learner "diagnostic": true), pace and the SLOW rule, re-teach methods remembered per learner (rules.json reteach), stars and streak, interest words first, GET /api/children/{id}/profile. Story phase: each learner's own story, then its quiz; the quiz moves the next story's level (rules.json story_quiz).
- Not wired yet: placement endpoint and session flow, end_with_easy_item, SLOW rule, alerts, seed_demo.py, model feedback wording, audio for model stories.
- Round 2 (2026-10-10): interest-ranked library/read-along stories and a personal story job at sign-up and session start; new English plots (animals, food, nature/farm, school/family) with word banks from existing content words; "letters" lesson style and the vowel intro; varied diagnostic items; progress_snapshots + GET /api/learners + existing_child_ids; level-matched sheet with parent_note; Gemini provider; sk_letters_2 tagged on 5 existing words (dahon, lapis, gatas, papel, pinto). Kiefer must confirm the parent footnote labels in rules.json practice_sheet.level_labels_fil ("Antas 1", "Antas 2").

## Working rules for the agent
- One task per prompt. Give a 5-bullet plan first for big tasks.
- Write tests before engine code. Run `python -m pytest` before saying a task is done.
- Only edit files in backend/, scripts/ and tests/ unless I say otherwise.
- If something fails 3 times, simplify it and tell me instead of adding complexity.
