Project: ReadingTutor PH. Offline tutor's assistant for DepEd ARAL-Reading, Key Stage 1, Filipino. One tutor, one laptop, 3 learners, 60 minutes or less. Fully offline.
I am Person 2. I own backend/, scripts/, tests/. Do not edit frontend/ or content/ (Person 1 and Person 3 own them).
Stack: Python FastAPI + Pydantic, SQLite, Ollama (3B instruct model, JSON output), MMS-TTS facebook/mms-tts-tgl.
Principles: rules decide what to teach. The model only writes stories, practice words, and summaries inside limits. Code checks every model output. Fixed templates are the fallback. No turn waits for the model; every turn returns in under 1 second.
Hard rules: no network calls except localhost. No new dependencies without asking. Do not rename JSON fields or ids from content/content.json and content/rules.json. ng is one tile. Learner data stays in the local SQLite file. Never invent Tagalog text; use only text from content files or templates I paste.
Layout: backend/main.py, db.py, content.py, engine/ (classifier, scoring, selector, rotation, review), llm/, tts/, tests/. scripts/pregen_audio.py, scripts/seed_demo.py.
API: POST /api/tutor/login; GET /api/groups/{id}; POST /api/groups; POST /api/sessions; GET /api/stories/{id}; POST /api/sessions/{id}/phase; GET /api/sessions/{id}/next; POST /api/sessions/{id}/answer; GET /api/sessions/{id}/summary; GET /api/children/{id}/sheet; GET /api/approvals; POST /api/approvals/{id}; GET /api/audio/{key}.wav.
Next turn: child_id, child_name, turn_number, task_type, item (id, prompt_audio, slots, tiles, syllables), support_level, prefill, seconds.
Answer: child_id, item_id, given, hints_used, attempt, time_ms.
Result: correct, mistake_type, feedback (message_fil, hint_fil), hint (kind, audio, highlight_slot), next_action (retry, show_answer, next), answer.
hint.kind: replay_by_syllable, highlight_slot, first_tile.
