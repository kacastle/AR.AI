# API contract

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
`interests` (optional, default `[]`): up to 3 ids from `content.json` → `interests` (`rules.json` → `personalization.max_interests_per_learner`), picked by the tutor at learner setup. The model writes personal stories only for learners with interests. Unknown ids or more than 3 → `422`.

Request
```json
{"tutor_name": "Teacher Liza", "learners": [
  {"name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": ["int_food", "int_toys"]},
  {"name": "Ben", "picture": "dog", "profile": "high_emergent", "interests": ["int_vehicles"]},
  {"name": "Mila", "picture": "star", "profile": "low_emergent"}
]}
```
Response: the group (same shape as GET below).

## GET /api/groups/{id}
```json
{"id": "g_e2c4a7a8", "tutor_name": "Teacher Liza", "learners": [
  {"id": "c_78552429", "name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": ["int_food", "int_toys"]},
  {"id": "c_937d2ee6", "name": "Ben", "picture": "dog", "profile": "high_emergent", "interests": ["int_vehicles"]},
  {"id": "c_7f05adfd", "name": "Mila", "picture": "star", "profile": "low_emergent", "interests": []}
]}
```

## POST /api/sessions
`present` = the learner ids at the session, in turn order. Turns rotate in this order.
`read_along_story_id` is the group's read-along story. `story_ids` gives each present learner the story for his or her story turn (rules.md section 9), chosen without the model in this order: an approved model story for that learner not read yet (`gs_…`) → a filled template from `content.json` `story_templates` at the learner's level, not used in the last 2 sessions (`ts_…`) → a library story at the learner's level (`st_…`). Fetch each with `GET /api/stories/{id}`.
Creating a session also asks the background model for practice words for each present learner (they show up in `GET /api/approvals` within a minute or two). Personal stories for the next session are asked for at the end of the session, when the phase becomes `summary`, right after the summary. None of this ever delays a request.

Request
```json
{"group_id": "g_e2c4a7a8", "present": ["c_78552429", "c_937d2ee6", "c_7f05adfd"]}
```
Response
```json
{"id": "s_97aadbd0", "group_id": "g_e2c4a7a8", "present": ["c_78552429", "c_937d2ee6", "c_7f05adfd"],
 "phase": "tiles", "read_along_story_id": "st_l1_001",
 "story_ids": {"c_78552429": "ts_69c7cdc1", "c_937d2ee6": "gs_84e95f95", "c_7f05adfd": "st_l1_002"}}
```

## GET /api/stories/{id}
`words` lists every word in reading order, with punctuation attached, for highlighting.
`id` can be a `content.json` story id (`st_…`), a filled template story (`ts_…`) or a model story the tutor approved (`gs_…`); the session's `story_ids` lists them. A model story that is waiting or rejected returns `404`: learners never see it before the tutor approves it. Model stories have their audio before they reach the tutor; a template story's audio is made in the background right after the session starts (`audio_url` is `404` for the first few seconds, and the timings are estimates until then).
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
`phase` is one of `tiles`, `stories`, `summary`. `ends_at` is local time with offset. The phase lengths come from `rules.json` → `session` (35 / 15 / 10 min). With `DEMO_FAST=1` (rules.json `session.demo_fast`) every phase is 1 minute and `/next` gives `seconds: 20`, so a demo session takes about 3 minutes.
Setting `summary` queues the model summary, then each learner's personal story for the next session.

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
- `gap_slot`: for `missing_letter`, the box (0-based) the learner fills; `null` for the other task types.
  Use it instead of guessing from `prefill`: at support `show` the prefill is the full word, and a letter
  can appear twice (in "unan" the gap is box 3, not box 1).
- `seconds`: time for the item.

```json
{"child_id": "c_78552429", "child_name": "Ana", "turn_number": 1, "task_type": "missing_letter",
 "item": {"id": "w_aso", "prompt_audio": "/api/audio/w_aso.wav", "slots": 3,
          "tiles": ["u", "a", "e", "i"], "syllables": ["a", "so"]},
 "support_level": "show", "prefill": ["a", "s", "o"], "gap_slot": 0, "seconds": 60}
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
Code computes every number (items correct of total, skills practiced, weakest skill, main mistakes, support level, alert). Moving the session to phase `summary` asks the background model to put them into words; its output must pass the checks (present child ids, real skill ids and methods, the same numbers, 25 words or fewer, no blocklist words), with one retry. Until it is ready, if it failed twice, if Ollama is off, and whenever answers were added after it was written, this returns the code template below (never waits for the model). Call it again a little later to get the model's wording; the shape is the same.
In the template, a learner with an alert (`rules.json` → `alert`: a skill below 0.60 after 10+ attempts or for 14 days) gets an extra sentence, for example `"Alert: Vowel sounds is still below 0.60."`.

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
With `AUTO_APPROVE=1` (demos only), checked model stories and words are approved when they are saved, so this list stays empty.
Model items waiting for the tutor, oldest first. Every item passed the checks in `content/test_prompts.py` (a failed one is retried once, then dropped). `kind`:
- `story`: a personal story, with its audio already made (`GET /api/audio/{payload.id}.wav`, so the tutor can listen before approving). `payload` has the same fields as content.json `stories` (`id` is `gs_…`, `source` is `"model"`), plus `model`, `plot_id` and `object`. Once approved, `GET /api/stories/{payload.id}` serves it, `approved_by_tutor` becomes `true`, and the learner gets it in the next session's `story_ids`.
- `words`: practice words. `payload` = `{"skill_id", "words": [{"text", "word_id", "syllables", "meaning_en"}], "model"}`; only content.json words. Once approved, they go on the learner's practice sheet while the learner is on that skill.

A learner gets no new story (or word list) while one is still waiting for the tutor.

Example from gemma4:e4b (`questions` and the second item shortened):
```json
[{"id": "a_5c1d9e20", "kind": "story", "child_id": "c_1ae8b7ec",
  "payload": {"id": "gs_3f8a61b2", "title": "Ang Bola ni Ana", "level": 1, "skill_ids": ["sk_vowels"],
              "target_word_ids": [], "interests": ["int_food", "int_toys"], "word_count": 40,
              "paragraphs": ["Nagdala si Ana ng bola. Sa parke niya ito dinala. Doon niya nakita si Kuya.",
                             "Si Kuya walang laruan. Kaya ibinahagi niya ang bola. Naglaro sila nang sabay.",
                             "Naglaro sila ng bola. Kaya sila ay umuwi. Masaya si Ana pagkatapos."],
              "questions": [{"type": "who", "prompt": "...", "choices": ["...", "...", "..."], "answer": "..."}],
              "source": "model", "reviewed": false, "approved_by_tutor": false,
              "model": "gemma4:e4b", "plot_id": "plot_l1_park", "object": "bola"}},
 {"id": "a_8e02b7c4", "kind": "words", "child_id": "c_1ae8b7ec",
  "payload": {"skill_id": "sk_vowels", "model": "gemma4:e4b",
              "words": [{"text": "oso", "word_id": "w_oso", "syllables": ["o", "so"], "meaning_en": "..."}]}}]
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
