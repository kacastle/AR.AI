# Model prompts (v0.2)

Four prompts run on the local 3B model in Ollama: **personal story**, **practice words**, **feedback**, and **tutor summary**. All stories are individual: one learner, one story. Each prompt returns JSON. Code checks every output before anyone sees it. If an output fails the checks 2 times, the app uses the fallback.

**Status:** Draft. Person 3 tests these prompts in hours 6–9 and updates this file with the final model choice and settings.

---

## 0. General rules

| Prompt | Temperature | Max tokens (`num_predict`) | When it runs | Fallback |
|---|---|---|---|---|
| Personal story | 0.5 | 600 | Background, end of session, one for each learner | A filled template from `story_templates` |
| Practice words | 0.3 | 300 | Background | Words from the skill's list in `content.json` |
| Feedback | 0.4 | 120 | Optional (see note) | `feedback_templates` in `rules.json` |
| Tutor summary | 0.3 | 400 | End of session | Fixed template (section 4) |

- **Turns never wait for the model.** During a turn, use `feedback_templates` from `rules.json` (less than 1 second). Use the feedback prompt only if a call takes less than 2 seconds on the demo laptop.
- Use Ollama's JSON output for all prompts: `"format": "json"`. For the personal story, pass a JSON schema as `format` (section 1), so the model cannot give the wrong number of paragraphs, questions, or choices. For practice words, pass a schema whose `text` is an enum of the candidates, with exactly `{count}` items (see `words_schema()` in `test_prompts.py`), so the model cannot invent a word or return too few.
- Turn off "thinking" for thinking models (Gemma 4): LM Studio `"reasoning_effort": "none"`, Ollama `"think": false`. Otherwise the model spends all of `max_tokens` on reasoning and returns no output.
- Use `keep_alive` (for example `"30m"`) so that the model stays loaded during a session. Load the model when the app starts.
- Instructions are in English; output is in Filipino. Small models follow English instructions better.
- Every model item gets `"source": "model"` and `"approved_by_tutor": false`. It goes to the approval queue.
- Check every text field against `safety.blocklist` in `rules.json`.
- Retry once with the same prompt if a check fails. After the second failure, use the fallback and log the failure.

### Ollama call (example)

```python
import requests, json

def call_model(system, user, temperature, num_predict, model="<model-name>", schema=None):
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": schema or "json",
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": temperature, "num_predict": num_predict},
    }, timeout=60)
    return json.loads(r.json()["message"]["content"])
```

The only network address is `localhost`. Nothing goes to the internet.

---

## 1. Personal story (guided)

Code chooses the plot, the object, the question types, and the example. The model only writes the plot in simple Filipino. This keeps the stories logical: small models write nonsense when they get long word lists and a free plot.

**Why the prompt has this shape (v0.2).** In v0.1, Gemma 3n passed 1 of 10 story checks, and its stories read like lists. The causes: (1) `"paragraphs": [""]` made it write one sentence per paragraph; (2) wide ranges ("4 to 8 sentences, 20–40 words") made it pad with filler; (3) the plots were lists of unrelated English events; (4) the examples had no linking words, and the Level 2 example was too long for its own checks. Now the model gets a fixed shape that it can count (paragraphs × 3 sentences), a plot in beats (one beat per paragraph), a Filipino word bank, linking words, and a full example output that passes every check. A JSON schema fixes the number of paragraphs, questions, and choices.

**Variables**

| Variable | Source |
|---|---|
| `{name}` | Learner's **first name only** |
| `{object}` | One item from `objects` of one of the learner's interests (`content.json` → `interests`). Rotate between sessions. |
| `{beats}` | `content.json` → `story_plots[].beats_en` at the learner's level, numbered "Paragraph 1: …", with `{name}` and `{object}` filled. Not the same plot as in the last 2 sessions. |
| `{word_bank}` | The plot's `word_bank_fil` |
| `{connectors}` | `rules.json` → `story_style.connectors_fil` |
| `{other_names}` | The plot's `characters` (for example "Nanay") |
| `{feeling_words}` | `rules.json` → `story_style.feeling_words_fil` (allowed answers for feeling questions) |
| `{distractor_names}` | `rules.json` → `personalization.neutral_distractor_names` (wrong choices for who questions) |
| `{paragraphs}`, `{sentences_per_paragraph}`, `{min_words}`, `{max_words}`, `{max_words_per_sentence}` | `rules.json` → `story_levels.<level>` |
| `{min_wps}`, `{max_wps}` | `rules.json` → `story_levels.<level>.target_words_per_sentence` |
| `{question_types}` | 3 types chosen by code from `story_levels.<level>.question_types`: first the `required_question_types` (Level 2: sequence, feeling), then random others |
| `{optional_words}` | 2 words from the learner's weakest skill. Optional: the model uses one only if it fits. |
| `{example_name}`, `{example_object}`, `{example_other_names}`, `{example_beats}`, `{example_json}` | `content.json` → `story_examples.<level>` (`example_json` = its `output`, as one line of JSON) |

**System**

```
You are a storyteller who writes short stories for Filipino children aged 6 to 8.
A teacher reads your stories aloud, so each sentence follows from the sentence before it.
Write in simple, natural Filipino (Tagalog). Never use English words.
Follow every rule. Output only valid JSON. No other text.
```

**User**

```
Write a short story in simple, natural Filipino (Tagalog) for a child aged 6 to 8.
The story is read aloud, so it must flow: each sentence follows from the sentence before it.

Main character: {name}. Object: {object}. Other characters (only these): {other_names}.
Plot. Write one paragraph for each part. Do not add other events, places, or characters.
{beats}

Shape:
- Exactly {paragraphs} paragraphs. Each paragraph has exactly {sentences_per_paragraph} sentences.
- Each sentence has {min_wps} to {max_wps} words, never more than {max_words_per_sentence}. Total {min_words} to {max_words} words.

Flow:
- After the first sentence, start most sentences with a linking word ({connectors}) or with siya, niya, sila.
- Write the name {name} in the first paragraph and in the last paragraph, as the person who does something in the sentence. Never add the name at the end of a sentence after a comma. In the other sentences, use siya or niya.
- Give each part of the plot time: the last paragraph finishes the plot; it does not jump to the end.
- Write the word "{object}" in the first paragraph and again in the last paragraph. In the last paragraph, write "{object}" itself, not "ito" or "niya".
- No filler sentences, no lesson, and no "Sana..." at the end. The last sentence ends the plot happily.

Words:
- Use only common words that a Grade 1 child knows. Use these words where they fit: {word_bank}.
- If it fits naturally, also use one of these words: {optional_words}. Do not force it.
- No English words. Use the past tense for things that happened.
- Write each name exactly as given (for example: si {other_names}, kay {other_names}). Never add -ng to a name (not "Kuyang").
- Kind and safe. No violence or fear.

Questions:
- Exactly 3 questions, with these types in this order: {question_types}.
- Each question has exactly 3 short, different choices in Filipino. Never 4.
- Copy the answer letter for letter from one of the choices.
- For who, what, where, and feeling questions, the answer uses words that are written in the story. Do not ask about something the story does not say.
- Write the questions after the story. For each question, first find the sentence in your story that has the answer, and copy the answer from that sentence. If no sentence has it, ask about something else.
- For a feeling question, the answer is one of these feeling words, and the story says it: {feeling_words}. Do not guess a feeling that the story does not say.
- For a where question, the answer is a place from the story and starts with "sa".
- In a who question, the 3 choices are people: {name}, {other_names}, or {distractor_names}.

Example. Main character: {example_name}. Object: {example_object}. Other characters: {example_other_names}.
{example_beats}
Output: {example_json}

Now write the story for {name}. Output only the JSON, in the same shape as the example.
```

Temperature: **0.5**. Send the JSON schema as Ollama `format` (see `story_schema()` in `test_prompts.py`): `paragraphs` has exactly `{paragraphs}` items, `questions` has exactly 3, each `choices` has exactly 3, and `type` is one of `{question_types}`.

**Checks**

- [ ] JSON parses; `title`, `paragraphs`, and 3 `questions` are present.
- [ ] Sentence count (`story_levels.<level>.min_sentences`–`max_sentences`), word count, and sentence length are in range. A line of dialogue with its speaker (`"Salamat!" sabi ni Lola.`) is one sentence.
- [ ] `{name}` appears 2 times or more; `{object}` appears 1 time or more.
- [ ] No person names except `{name}` and `{other_names}`.
- [ ] Each `answer` is one of its `choices`; the 3 choices are different; each `type` is allowed.
- [ ] For `who`, `what`, and `where` questions, the answer is in the story text.
- [ ] No blocklist word.
- [ ] The Filipino speaker's rating (in tests) is 4 or more for "makes sense."

**After the checks:** the paragraphs from the model are used as they are. Add `id`, `level`, `skill_ids`, `for_child_id`, `plot_id`, `source: "model"`, `approved_by_tutor: false`. Generate audio in the background.

**Fallback:** fill a template from `content.json` → `story_templates` at the learner's level (see `rules.md` section 9).

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
Select exactly {count} different words, only from the candidates. Copy each word letter for letter.
Never add a word that is not in the candidate list, even if it fits the skill.
Candidates: {candidate_words}
Output JSON, for example:
{"words": [{"text": "bahay", "meaning_en": "house"}]}
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
- Be kind and short. Each field is one short sentence of 8 words or fewer (never more than 12).
- Never say that the child is bad or slow.
- Do not give the full answer unless the attempt is 3: never write the word "{expected}", not even in syllables (not "{expected}" split with hyphens or spaces). The app plays the sound; your hint tells the child what to listen for or look at.
- Only Filipino words. No English or Taglish (not "clap", say "pumalakpak").
- Talk about the sound or the letter, not the word. Good: {"message_fil": "Malapit na, {name}!", "hint_fil": "Pakinggan ang huling tunog."}
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
c_01 | Ana | 7 of 8 correct | skills: sk_cvcv_1 (CV-CV words), sk_ng (The letter ng) | weakest: sk_ng (The letter ng) | mistakes: O_NG (ng written as n, or as n + g) x2 | support: guide | alert: no
```

Each code goes with its meaning (`skills[].name_en` in `content.json`, `mistake_types.<code>.description_en` in `rules.json`). Without the meaning, the model guesses what a code means and writes wrong facts in the summary.

**User**

```
Write a session summary for an ARAL-Reading tutor, in simple English.
Session date: {date}. Learners present: {present_count}.
For each learner you get: id, name, items correct of total, skills practiced,
weakest skill, main mistake types, support level, and alert yes or no.
{learner_data}
Allowed next focus skills (id and meaning): {skill_list}
Allowed next methods: {method_list}
Rules:
- `child_id` is the id exactly as given (c_01), not the name.
- next_focus_skill is one skill id copied from the allowed list (for example sk_ng). next_method is one method id copied from the allowed list.
- Each summary is one or two short sentences, 20 words or fewer. Start with the learner's name. Only say what the data says.
- In the summary, write skills, mistakes, and methods in plain words for the tutor, using the meanings given. Never write ids such as sk_ng, O_NG, or ng_sound_pairs in the summary text.
- Use numbers like "6 of 8 correct". No percentages.
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
