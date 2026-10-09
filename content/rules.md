# Adaptive rules (v0.2)

This file explains `rules.json`. The code reads all numbers from `rules.json`. Do not put these numbers in the code.

Rules decide what to teach, how difficult, how to teach, and when to review. The local model only writes content inside the limits that the rules set.

---

## 1. Decision loop (one answer)

1. Select the skill: a due review skill first, else the weakest unlocked skill.
2. Select a task type for the skill category (`selection.task_types_by_category`) and an item at the current difficulty.
3. The learner answers.
4. Classify the answer (section 7).
5. Give feedback immediately with `feedback_templates`. If wrong, run the correction procedure (section 6).
6. Update the skill score, the support level, and the difficulty.
7. Schedule a review if the skill is mastered.
8. Write one answer event to SQLite.

A skill is **unlocked** when all of its `prerequisites` (in `content.json`) are mastered. Skills with no prerequisites are always unlocked.

## 2. Skill score

Each skill has a score from 0 to 1. New skills start at `score.start_score`.

```
score_new = score_old + alpha * (result - score_old)      # alpha = 0.3
```

| Answer | result |
|---|---|
| Correct, no hint, support level `alone` | 1.0 |
| Correct after 1 hint, or at support level `guide` | 0.7 |
| Correct only after the answer was shown (rebuild) | 0.4 |
| Wrong | 0.0 |

## 3. Thresholds

| State | Rule | Action |
|---|---|---|
| Reteach | score < 0.60 | Teach again with the method for the main mistake; support level `show` |
| Practice | 0.60 ≤ score < 0.85 | More items, same method |
| Mastered | score ≥ 0.85 **and** attempts ≥ 8 **and** last 3 correct | Unlock next skills; start review |
| Alert | score < 0.60 after 10+ attempts, or for 14 days | Add to the tutor summary and the next-session plan |

## 4. Support levels and difficulty

| Level | What the app does | Move up | Move down |
|---|---|---|---|
| `show` | Shows the full answer first; the learner then builds it | 3 correct in a row | — |
| `guide` | Prefills the first tile | 3 correct in a row | 2 wrong in a row |
| `alone` | No help | — | 2 wrong in a row |

Difficulty: keep accuracy over the last 10 answers between 70% and 85%.

- Above 90%: more syllables, more distractor tiles (2 → 3 → 4), or the next story level.
- Below 60%: fewer syllables, fewer distractor tiles, more support.
- 3 wrong in a row: stop the skill, give 1 easy item from a mastered skill, then return.

## 5. ARAL session, rotation, placement, review

**Session (60 minutes or less):**

| Minutes | Activity |
|---|---|
| 0–35 | Tile turns: 1 warm-up review item, then about 9 items for each learner |
| 35–50 | Story turns: each learner, in turn, listens to his or her own personal story with word highlights, then answers 3 questions |
| 50–60 | Tutor summary and practice sheets |

All work is individual. There is no group reading. Each learner gets one personal story in each session.

The last turn of each learner is an easy item. If fewer learners are present, each learner gets more items. With `DEMO_FAST=1`, use `session.demo_fast`.

**Rotation:** fixed order (for example Ana → Ben → Mila), skip absent learners. Each turn is for that learner's own weakest due skill. After 3 wrong answers in a row, the learner's next turn is an easy item.

**Placement (first session, in turns):** 2 items for each skill in `placement.skills`, in order. Stop after 2 skills fail in a row. Passed skills get score 0.70. Practice starts at the first failed skill. Profile: `low_emergent` if the learner fails before `sk_cvcv_1`, else `high_emergent`. The tutor can change the profile to match the school's CRLA result.

**Review:** after mastery, review after 1, 3, 7, and 14 days. A correct review goes to the next step. A wrong review sets the score to 0.70, puts the skill back in practice, and restarts the steps.

## 6. Correction procedure

1. Feedback immediately (`message_fil` + `hint_fil` from `feedback_templates`).
2. Attempt 1 wrong → hint `replay_by_syllable` (play the slow audio).
3. Attempt 2 wrong → hint `highlight_slot` (the first wrong slot).
4. Attempt 3 wrong → hint `first_tile`.
5. Still wrong → `show_answer_then_rebuild`: show the answer (`SHOW_ANSWER` template), then the learner must build it again. Never only show the answer.
6. Then give 1 new item with the same pattern to check the learning.
7. After a mistake type repeats, use its method (`mistake_types.<code>.method`) for the next `items_after` items.

## 7. Classifier specification

Input: `expected` tiles, `given` tiles, task type. Work in this order and stop at the first match.

1. `given == expected` → correct.
2. **Comprehension task:** question `type` `who`/`where`/`what` → `C_LITERAL`; `sequence` → `C_SEQUENCE`; `feeling`/`main_idea` → `C_INFER`.
3. **Sentence task:** same words in a different order → `SN_ORDER`; else a capital letter or the period differs → `SN_PUNCT`.
4. Time over `timing.slow_seconds` with no answer → `SLOW`.
5. **ng check:** expected has `ng` at a position, and given has `n` there, or `n` then `g` → `O_NG`.
6. **Same tiles, different order** → `O_ORDER`. (Plain Levenshtein reads a swap as 2 substitutions, so check this first.)
7. Align with Levenshtein on tiles, then:
   - Only deletions, and the deleted tiles are one full syllable of the word → `S_SYLL_MISS`.
   - One deletion at the last position → `P_OMIT_FINAL`.
   - Other deletions → `P_OMIT_MID`.
   - Only insertions → `P_ADD`.
   - One substitution: vowel ↔ vowel → `P_SUB_VOWEL`; consonant ↔ consonant → `P_SUB_CONS`.
   - Mixed operations → classify the leftmost operation; add the others to `mistake_counts`.

**Required tests:**

| Expected | Given (tiles) | Code |
|---|---|---|
| mesa | m·i·s·a | `P_SUB_VOWEL` |
| bata | d·a·t·a | `P_SUB_CONS` |
| bahay | b·a·h·a | `P_OMIT_FINAL` |
| kandila | k·a·d·i·l·a | `P_OMIT_MID` |
| mata | m·a·t·a·a | `P_ADD` |
| ibon | i·b·n·o | `O_ORDER` |
| ngipin | n·i·p·i·n | `O_NG` |
| ngipin | n·g·i·p·i·n | `O_NG` |
| sapatos | s·a·p·o·s | `S_SYLL_MISS` |
| Si Ana ay nasa bahay. | bahay. · Si · Ana · ay · nasa | `SN_ORDER` |

## 8. Feedback template placeholders

| Placeholder | Value | Example (bahay) |
|---|---|---|
| `{name}` | Learner's name | Ben |
| `{syllables_hyphen}` | Syllables joined with hyphens | ba-hay |
| `{syllables_last_caps}` | Same, last syllable in capitals | ba-HAY |
| `{slots}` | Number of tiles in the answer | 5 |

`CORRECT.message_fil` has 3 options. Rotate them so the learner does not hear the same line every time.

## 9. Personalization (name and interests)

Settings are in `rules.json` → `personalization`. The interest catalog is in `content.json` → `interests`.

**Collect interests**

- At learner setup, the tutor picks up to 3 interests for each learner from the catalog (picture + label). Or, in the first session, the learner taps up to 3 interest pictures.
- Store them in the child profile: `"interests": ["int_animals", "int_basketball"]`.

**Which story the app uses**

Each learner gets one personal story in each session, during his or her story turn. The learner is the main character. Code chooses a plot from `story_plots` (not used in the last 2 sessions) and one object from the learner's interests; the model only writes that plot in Filipino (see `prompts.md` section 1).

**Story shape (so the story flows when read aloud)**

- Each plot in `story_plots` has `beats_en`: one beat for each paragraph (3 beats at both levels; Level 1 has shorter sentences). Level 1 had 2 beats until v0.3; the review found those stories too abrupt. The beats go beginning → problem or turn → happy ending, and each beat leads to the next one ("so", "but", "then").
- The `{object}` matters in the first and the last beat. Do not write a plot in which the object appears once and is then forgotten.
- Each plot has `word_bank_fil`: correct Filipino words for that plot (for example `tanghalian`, not "lunch"; `gumuhit`, not "nag-drawing"). Small models invent verb forms when they do not get these words.
- The numbers are in `rules.json` → `story_levels.<level>`: `paragraphs`, `sentences_per_paragraph`, `target_words_per_sentence`, `min_sentences`/`max_sentences`, and `required_question_types`. Linking words are in `story_style.connectors_fil`.
- A new plot needs `id`, `level`, `characters`, `beats_en`, `word_bank_fil`, and `outline_en` (= the beats joined).
- `fits_objects`: the interest objects that make sense in this plot (you play with a ball at the park, not with shoes; you draw with crayons, not in the rain). Code chooses a plot that fits one of the learner's interest objects, then one of those objects. A new object must be added to the `fits_objects` of the plots it fits, or code never uses it.
- Never use `laruang` + an animal (laruang pusa, laruang aso...): it does not read as a toy, and "laruang pusa" can read as an innuendo (Filipino speaker's review, r4).

**Fallback order:** an approved model story for that learner → a filled template from `story_templates` → a library story. Templates need no model, so personalization always works.

**Filling a template (code)**

1. `{name}` = the learner's first name.
2. `{object}` = one item from `objects` of one of the learner's interests. Rotate the interests between sessions.
3. `{other_object_1}`, `{other_object_2}` = objects from other interests (wrong choices).
4. Use a template at the learner's level that the learner did not get in the last 2 sessions.

**Safety and privacy rules**

- First names only. Never a surname, school name, address, real family names, health or family problems, or comparisons between learners.
- A named learner is always kind and successful. Problems come from weather, a lost object, or chance, never from the learner.
- Wrong name choices in questions come only from `neutral_distractor_names` (Lola, Tatay, Kuya...), never from other learners' names.

## 10. Notes

- All Filipino lines in `feedback_templates` are drafts. A Filipino speaker must check them.
- `safety.blocklist` is a starter list. Person 3 extends it.
- `safety.judgmental_en` and `safety.judgmental_fil` are words that judge the learner (slow, mabagal, tamad...). Any match rejects a feedback or tutor summary output.
- Each `story_examples.<level>.output` in `content.json` must pass `check_story` in `test_prompts.py`. The model copies the length and shape of the example, so an example that breaks the rules teaches the model to break them.
- The v0.2 examples, plot beats, and word banks are drafts. A Filipino speaker must check them.
- If `rules.json` changes, restart the backend. Do not edit numbers in the code.
