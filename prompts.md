# Model prompts (v0.1)

Four prompts run on the local 3B model in Ollama: **personal story**, **practice words**, **feedback**, and **tutor summary**. All stories are individual: one learner, one story. Each prompt returns JSON. Code checks every output before anyone sees it. If an output fails the checks 2 times, the app uses the fallback.

**Status:** Draft. Person 3 tests these prompts in hours 6–9 and updates this file with the final model choice and settings.

---

## 0. General rules

| Prompt | Temperature | Max tokens (`num_predict`) | When it runs | Fallback |
|---|---|---|---|---|
| Personal story | 0.7 | 600 | Background, end of session, one for each learner | A filled template from `story_templates` |
| Practice words | 0.3 | 300 | Background | Words from the skill's list in `content.json` |
| Feedback | 0.4 | 120 | Optional (see note) | `feedback_templates` in `rules.json` |
| Tutor summary | 0.3 | 400 | End of session | Fixed template (section 4) |

- **Turns never wait for the model.** During a turn, use `feedback_templates` from `rules.json` (less than 1 second). Use the feedback prompt only if a call takes less than 2 seconds on the demo laptop.
- Use Ollama's JSON output for all prompts: `"format": "json"` (or a JSON schema).
- Use `keep_alive` (for example `"30m"`) so that the model stays loaded during a session. Load the model when the app starts.
- Instructions are in English; output is in Filipino. Small models follow English instructions better.
- Every model item gets `"source": "model"` and `"approved_by_tutor": false`. It goes to the approval queue.
- Check every text field against `safety.blocklist` in `rules.json`.
- Retry once with the same prompt if a check fails. After the second failure, use the fallback and log the failure.

### Ollama call (example)

```python
import requests, json

def call_model(system, user, temperature, num_predict, model="<model-name>"):
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": "json",
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_predict": num_predict},
    }, timeout=60)
    return json.loads(r.json()["message"]["content"])
```

The only network address is `localhost`. Nothing goes to the internet.

---

## 1. Personal story (learner's name and interests)

The learner is the main character. The story uses words from the learner's interests.

**Variables**

| Variable | Source |
|---|---|
| `{name}` | Learner's **first name only** |
| `{interest_labels}` | `label_en` of the learner's interests in `content.json` → `interests` (for example "Animals, Basketball") |
| `{interest_words}` | `words` + `objects` of those interests (for example "aso, pusa, tuta, bola, laro") |
| `{level}` | Learner's current level |
| `{min_words}`, `{max_words}`, `{max_words_per_sentence}`, `{question_types}` | `rules.json` → `story_levels.<level>` |
| `{min_sentences}`, `{max_sentences}` | Level 1: 4–6; Level 2: 8–10 |
| `{target_words}` | 2–3 words from the learner's weakest skill (`content.json`) |
| `{known_words}` | Up to 20 words from mastered skills |
| `{setting}` | One of: bahay, palengke, ilog, bukid, kubo, paaralan, parke |
| `{level_rule}` | Level 2: "One small problem and a happy ending. The problem comes from weather, a lost object, or chance, never from {name}. {name} helps solve it." Level 1: empty |
| `{other_names}` | Up to 2 names from `personalization.neutral_distractor_names` |

**System**

```
You write short stories for Filipino children aged 6 to 8.
Write in simple, natural Filipino (Tagalog).
Follow every rule. Output only valid JSON. No other text.
```

**User**

```
Write one story about a child named {name}.
{name} likes: {interest_labels}.
Use at least 2 of these interest words: {interest_words}
Level: {level}. Use {min_sentences} to {max_sentences} sentences and {min_words} to {max_words} words.
Use ALL of these target words: {target_words}
Prefer these known words: {known_words}
Setting: {setting}
Other characters may only be: {other_names}.
Rules:
- {name} is the main character. Use the name {name} at least 2 times.
- {name} is kind, brave, and successful in the story.
- Each sentence has {max_words_per_sentence} words or fewer.
- Safe topics only: family, animals, food, play, helping, weather.
- No violence, fear, death, romance, brand names, or real people.
- Do not add a surname, a school name, or a place name that is not in the setting.
- {level_rule}
- Write exactly 3 questions of these types: {question_types}.
- Each question has 3 short choices. Exactly one choice is correct.
- If a choice is a person, use {name} or one of: {other_names}.
Output JSON:
{"title": "", "paragraphs": [""], "questions": [{"type": "", "prompt": "", "choices": ["", "", ""], "answer": ""}]}
```

**Checks**

- [ ] JSON parses; `title`, `paragraphs`, and 3 `questions` are present.
- [ ] `{name}` appears 2 times or more.
- [ ] 2 or more interest words appear (substring match, so "nagbasketbol" counts for "basketbol").
- [ ] No person names except `{name}` and `{other_names}` (check capitalized words against a list of allowed words).
- [ ] Word count is between `min_words` and `max_words`; each sentence has `max_words_per_sentence` words or fewer.
- [ ] All target words are in the story.
- [ ] Each `answer` is one of its `choices`; the 3 choices are different; each `type` is allowed.
- [ ] No blocklist word.

**After the checks:** split the story into paragraphs of 2–3 sentences. Add `id`, `level`, `skill_ids`, `target_word_ids`, `for_child_id`, `source: "model"`, `approved_by_tutor: false`. Generate audio in the background.

**Fallback:** fill a template from `content.json` → `story_templates` at the learner's level (see `rules.md` section 9). Use a library story only if no template fits.

---

## 2. Practice words

A 3B model can invent words that do not exist. So **code** makes the candidate list, and the model only selects and splits.

**Code first**

1. Take a Tagalog word list (record its source and license in the disclosure list) and the words in `content.json`.
2. Keep words that use only allowed tiles and match the skill pattern (for example: ends in a consonant for `sk_cvc_final`; contains `ng` for `sk_ng`).
3. Remove words the child saw in the last session.
4. Send up to 40 candidates.

**User**

```
From the candidate list, select {count} words for a child aged 6 to 8.
Skill: {skill_name_en} ({pattern_description})
The child's mistake: {mistake_description}
Prefer common, concrete words that a child can picture.
Do not select words that are rude, scary, or for adults.
Split each word into syllables.
Candidates: {candidate_words}
Output JSON:
{"words": [{"text": "", "syllables": [""], "meaning_en": ""}]}
```

**Checks**

- [ ] Each `text` is in the candidate list.
- [ ] The joined `syllables` equal `text`.
- [ ] No blocklist word.
- [ ] Code (not the model) makes `tiles` (with `ng` as one tile) and `distractor_tiles` (from `confusable_letters` in `rules.json`).

**Fallback:** words from the skill's list in `content.json`.

---

## 3. Feedback (optional)

**User**

```
Write feedback for a child aged 6 to 8, in simple Filipino.
Child name: {name}
Task: {task_type}. Expected: {expected}. Child wrote: {given}.
Mistake type: {mistake_description}
Teaching method: {method_description}
Attempt: {attempt} of 3. Support level: {support_level}
Rules:
- Be kind and short. Each field has 12 words or fewer.
- Never say that the child is bad or slow.
- Do not give the full answer unless the attempt is 3.
Output JSON:
{"message_fil": "", "hint_fil": ""}
```

**Checks**

- [ ] Each field has 12 words or fewer.
- [ ] The full answer is not in the text before attempt 3.
- [ ] No blocklist word.

**Fallback:** `feedback_templates` in `rules.json`. (For the demo, use the templates.)

---

## 4. Tutor summary

Code computes all numbers first. The model only puts them into words.

**`{learner_data}` format (one line for each learner, made by code)**

```
c_01 | Ana | 7 of 8 correct | skills: sk_cvcv_1, sk_ng | weakest: sk_ng | mistakes: O_NG x2 | support: guide | alert: no
```

**User**

```
Write a session summary for an ARAL-Reading tutor, in simple English.
Session date: {date}. Learners present: {present_count}.
For each learner you get: id, name, items correct of total, skills practiced,
weakest skill, main mistake types, support level, and alert yes or no.
{learner_data}
Allowed next methods: {method_list}
Rules:
- One line for each learner, 25 words or fewer.
- Use numbers like "6 of 8 correct". No percentages.
- Name one next focus skill and one method from the allowed list.
- If 2 or more learners have the same main mistake, write one short note to the tutor about it.
- Kind and factual. Never call a learner slow, weak, or bad.
Output JSON:
{"learners": [{"child_id": "", "summary": "", "next_focus_skill": "", "next_method": ""}], "group_note": ""}
```

`{method_list}` = the keys of `methods` in `rules.json`.

**Checks**

- [ ] Each `child_id` is a learner who was present; no learner is missing.
- [ ] `next_focus_skill` is a skill id in `content.json`; `next_method` is a key in `rules.json` → `methods`.
- [ ] The numbers in each `summary` match the computed numbers.
- [ ] Each summary has 25 words or fewer; no blocklist word.

**Fallback template (code only)**

```
{name}: {correct} of {total} correct. Next: {weakest_skill_name_en} with {method_description_short}.
```

Tutor note (`group_note`) fallback: if 2+ learners share a main mistake → "{names} need more work on {mistake_description}."

**Example output**

```json
{
  "learners": [
    {"child_id": "c_01", "summary": "Ana: 7 of 8 correct. Strong with CV-CV words. Next: the letter ng with ng sound pairs.", "next_focus_skill": "sk_ng", "next_method": "ng_sound_pairs"},
    {"child_id": "c_02", "summary": "Ben: 4 of 8 correct. Often leaves out the last sound (bahay to baha). Next: final consonants with syllable clapping.", "next_focus_skill": "sk_cvc_final", "next_method": "syllable_color_clap"},
    {"child_id": "c_03", "summary": "Mila: 5 of 8 correct. Mixes e and i. Next: CV syllables with vowel pairs.", "next_focus_skill": "sk_cv_1", "next_method": "minimal_pair_vowels"}
  ],
  "group_note": "Ben and Mila both need syllable work. Plan syllable items in each of their turns."
}
```

---

## 5. Practice sheet (code, no model)

One printable page for each learner. Settings are in `rules.json` → `practice_sheet`.

- Learner's name and the date.
- 5 words from the learner's next focus skill, large letters, syllables marked (ba · hay).
- 1 sentence from `content.json` → `sentences`.
- The fixed home line: `practice_sheet.home_line_fil`.
- No scores on the sheet.

---

## 6. Test plan (Person 3, hours 6–9)

- [ ] Run each prompt 10 times with different inputs on the demo laptop.
- [ ] Record the check pass rate and the seconds for each call.
- [ ] A Filipino speaker rates each story from 1 to 5 for natural Filipino and for child safety.
- [ ] Test 2–3 small models; keep the one with the best Filipino.
- [ ] Write the final model name, settings, and results here.

| Model | Story pass rate | Avg seconds (story) | Filipino rating (1–5) | Chosen |
|---|---|---|---|---|
| | | | | |
