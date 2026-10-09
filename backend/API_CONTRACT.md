# API contract (P2-1)

Base URL: `http://localhost:8000`. All bodies are JSON. CORS allows `http://localhost:5173`.
Live, clickable docs: `http://localhost:8000/docs`.

The examples below are real responses from the server. Ids (`g_…`, `c_…`, `s_…`) are random per database.

Errors: `404` unknown id, `409` answer for a turn that is not the current one, `422` bad body. The error body is always `{"detail": "..."}`.

---

## POST /api/tutor/login
Demo stub: any PIN is accepted.

Request
```json
{"pin": "1234"}
```
Response
```json
{"ok": true}
```

## POST /api/groups
`profile` must be `low_emergent` or `high_emergent` (`rules.json` → `placement.profiles`). `picture` is any string the frontend chooses (for example an icon name).

Request
```json
{"tutor_name": "Teacher Liza", "learners": [
  {"name": "Ana", "picture": "cat", "profile": "low_emergent"},
  {"name": "Ben", "picture": "dog", "profile": "high_emergent"},
  {"name": "Mila", "picture": "star", "profile": "low_emergent"}
]}
```
Response: the group (same shape as GET below).

## GET /api/groups/{id}
```json
{"id": "g_e2c4a7a8", "tutor_name": "Teacher Liza", "learners": [
  {"id": "c_78552429", "name": "Ana", "picture": "cat", "profile": "low_emergent"},
  {"id": "c_937d2ee6", "name": "Ben", "picture": "dog", "profile": "high_emergent"},
  {"id": "c_7f05adfd", "name": "Mila", "picture": "star", "profile": "low_emergent"}
]}
```

## POST /api/sessions
`present` = the learner ids at the session, in turn order. Turns rotate in this order.

Request
```json
{"group_id": "g_e2c4a7a8", "present": ["c_78552429", "c_937d2ee6", "c_7f05adfd"]}
```
Response
```json
{"id": "s_97aadbd0", "group_id": "g_e2c4a7a8", "present": ["c_78552429", "c_937d2ee6", "c_7f05adfd"],
 "phase": "tiles", "read_along_story_id": "st_l1_001"}
```

## GET /api/stories/{id}
`words` lists every word in reading order, with punctuation attached, for highlighting.
`words` is every word in reading order. Once `scripts/pregen_audio.py` has run, `start_ms`/`end_ms` are the real positions of each word in `audio_url` (the story is read naturally, paragraph by paragraph with a short pause between; the timings come from the voice model), so tapping a word can play just that part. Before that they are estimates and `audio_url` returns 404.

```json
{"title": "Ang Bahay ni Ana",
 "paragraphs": ["Si Ana ay may bahay. Malaki ang bahay ni Ana.",
                "May aso si Ana. Bantay ang pangalan ng aso.",
                "Masaya si Ana at si Bantay sa bahay."],
 "words": [{"text": "Si", "start_ms": 0, "end_ms": 310},
           {"text": "Ana", "start_ms": 460, "end_ms": 850},
           {"text": "ay", "start_ms": 1000, "end_ms": 1310}],
 "audio_url": "/api/audio/st_l1_001.wav"}
```
(`words` is shortened here.)

## POST /api/sessions/{id}/phase
`phase` is one of `tiles`, `stories`, `summary`. `ends_at` is local time with offset. The phase lengths come from `rules.json` → `session` (35 / 15 / 10 min; 1 min each with `DEMO_FAST=1`).

Request
```json
{"phase": "tiles"}
```
Response
```json
{"phase": "tiles", "ends_at": "2026-10-09T18:23:12+08:00"}
```

## GET /api/sessions/{id}/next
The current turn. Calling it again returns the same turn until it is answered with `next_action: "next"`.
Learners take turns in the group's fixed order, and absent learners are skipped.
- `task_type`:
  - `dictation_letters`: build the word from letter tiles.
  - `dictation_syllables`: build it from syllable tiles.
  - `missing_letter`: one box is empty; pick the tile for it.
  - `sentence_builder`: put word tiles in order (`syllables` is `[]`).
- `item.slots`: number of answer boxes.
- `item.tiles`: tiles to choose from, shuffled: answer tiles and distractors. For `missing_letter`, these are the candidates for the empty box. `ng` is one tile; words with `ng` always get `n` and `g` as distractors.
- `prefill`: **one entry per box**, `""` = empty box.
  - `show`: the full answer (the learner then rebuilds it).
  - `guide`: first tile, e.g. `["b","","","",""]`.
  - `alone`: all `""`.
  - For `missing_letter`, every box except the gap is filled (`["","s","o"]`).
- `seconds`: time for the item.

```json
{"child_id": "c_78552429", "child_name": "Ana", "turn_number": 1, "task_type": "missing_letter",
 "item": {"id": "w_aso", "prompt_audio": "/api/audio/w_aso.wav", "slots": 3,
          "tiles": ["u", "a", "e", "i"], "syllables": ["a", "so"]},
 "support_level": "show", "prefill": ["a", "s", "o"], "seconds": 60}
```

## POST /api/sessions/{id}/answer
`given` is the content of **all** boxes, left to right (for `missing_letter` too: the full word). `attempt` starts at 1 for each item and goes up by 1 on each retry. The skill score and support level update once, when the item ends (`next_action: "next"`).

Request
```json
{"child_id": "c_78552429", "item_id": "w_aso", "given": ["a", "s", "u"], "hints_used": 0, "attempt": 1, "time_ms": 4200}
```

What happens on each attempt:

| Attempt | Wrong → `next_action` | `hint.kind` |
|---|---|---|
| 1 | `retry` | `replay_by_syllable` (`hint.audio` = slow audio) |
| 2 | `retry` | `highlight_slot` (`hint.highlight_slot` = first wrong box, 0-based) |
| 3 | `retry` | `first_tile` (`highlight_slot` = 0) |
| 4 | `show_answer` | `hint` is null; `answer` has the tiles. The learner must rebuild, then send attempt 5 |
| 5+ | `next` | `hint` is null. The item ends as wrong; call `/next` for the next learner |

Correct at any attempt → `next_action: "next"`, then call `/next` for the next learner.

`mistake_type` is a code from `rules.json` → `mistake_types` on every wrong answer (null when correct). Sentence items (`sentence_builder`) get `SN_ORDER` or `SN_PUNCT`. `feedback` is the fixed template from `rules.json` → `feedback_templates` for that code, with the learner's name and the item's syllables filled in (rules.md section 8). A code without a template gets `"Subukan natin ulit, {name}!"` and a null `hint_fil`. Attempt 4 uses `SHOW_ANSWER`; attempt 5+ uses the mistake's `message_fil` only. Correct answers rotate the `CORRECT` lines.

Wrong, attempt 2 (`given` `["a", "s", "u"]` for aso):
```json
{"correct": false, "mistake_type": "P_SUB_VOWEL",
 "feedback": {"message_fil": "Magaling ang subok mo!", "hint_fil": "Pakinggan: a-so. Aling patinig ang tama?"},
 "hint": {"kind": "highlight_slot", "audio": null, "highlight_slot": 2},
 "next_action": "retry", "answer": null}
```
Wrong, attempt 4:
```json
{"correct": false, "mistake_type": "P_SUB_VOWEL",
 "feedback": {"message_fil": "Tingnan ang tamang sagot.", "hint_fil": "Ngayon, ikaw naman ang bumuo."},
 "hint": null, "next_action": "show_answer", "answer": ["a", "s", "o"]}
```
Correct:
```json
{"correct": true, "mistake_type": null,
 "feedback": {"message_fil": "Ang galing mo, Ana!", "hint_fil": null},
 "hint": null, "next_action": "next", "answer": null}
```
Every answer writes one row to the `events` table, with `session_id` and `turn_number`. No turn calls the model.

## GET /api/sessions/{id}/summary
One entry per present learner. `next_focus_skill` is a skill id from content.json, and `next_method` is a key of `rules.json` → `methods`. `group_note` is `""` when there is nothing to note.

```json
{"learners": [
  {"child_id": "c_78552429", "summary": "Ana: 0 of 1 correct. Next: Vowel sounds with minimal pair vowels.",
   "next_focus_skill": "sk_vowels", "next_method": "minimal_pair_vowels"},
  {"child_id": "c_937d2ee6", "summary": "Ben: 0 of 0 correct. Next: Vowel sounds with minimal pair vowels.",
   "next_focus_skill": "sk_vowels", "next_method": "minimal_pair_vowels"}
 ],
 "group_note": ""}
```

## GET /api/children/{id}/sheet
Printable practice sheet. No scores.

```json
{"name": "Ana", "date": "2026-10-09",
 "words": [{"text": "aso", "syllables": ["a", "so"]}, {"text": "ahas", "syllables": ["a", "has"]},
           {"text": "elepante", "syllables": ["e", "le", "pan", "te"]},
           {"text": "eroplano", "syllables": ["e", "ro", "pla", "no"]}, {"text": "ibon", "syllables": ["i", "bon"]}],
 "sentence": "Si Ana ay nasa bahay.",
 "home_line_fil": "Basahin nang malakas ang mga salitang ito kasama ang isang kasama sa bahay."}
```

## GET /api/approvals
AI items waiting for the tutor. The list is empty until the model step is built. `kind` is `story`, `words` or `summary`. `payload` is the item's JSON (for a story: the same fields as in content.json `stories`).

```json
[{"id": "a_1b2c3d4e", "kind": "story", "child_id": "c_78552429",
  "payload": {"title": "...", "paragraphs": ["..."], "questions": []}}]
```

## POST /api/approvals/{id}
Request
```json
{"approve": true}
```
Response
```json
{"ok": true}
```

## GET /api/audio/{key}.wav
Returns `audio/wav` (16 kHz mono), made by `python scripts/pregen_audio.py`. 404 if the clip was not generated, 400 for a bad key. Keys:

| Key | Audio |
|---|---|
| `w_aso` (any word or syllable item id) | the item, `prompt_audio` |
| `w_aso_slow` | the item syllable by syllable with short gaps (`hint.audio` for `replay_by_syllable`) |
| `syl_so` | one syllable tile |
| sentence id, and `{id}_slow` | the sentence, and word by word |
| `st_l1_001` (story id) | the whole story read naturally; matches the story's `words` timings |
| `st_l1_001_p1` | one story paragraph, numbered from 1 |
| `fb_CORRECT_2`, `fb_SHOW_ANSWER_hint` | a fixed feedback line (`message_fil[i]` or `hint_fil`). Lines with `{name}` or syllables in them have no audio |
