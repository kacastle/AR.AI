#!/usr/bin/env python3
"""
Prompt test harness for Reading Tutor PH.

Reads the prompts directly from prompts.md, fills them with test learners,
calls the local Ollama model, runs the checks from prompts.md, and saves:
  - results.csv              one row per run (pass/fail, failed checks, seconds)
  - stories_for_review.md    every story, for the Filipino speaker to rate 1-5

Usage (from the folder with content.json, rules.json, prompts.md):
  Ollama (default; model gemma4:e4b, first: ollama pull gemma4:e4b):
    python test_prompts.py --runs 10
    python test_prompts.py --list-models
  One prompt only:
    python test_prompts.py --prompt story --runs 5
  Second seed (to confirm a pass rate):
    python test_prompts.py --runs 10 --seed 2
  LM Studio instead (start the local server in LM Studio first):
    python test_prompts.py --backend lmstudio --model google/gemma-4-e4b --runs 10
  No model (self-test of this script):
    python test_prompts.py --mock

No extra packages are necessary (standard library only).
"""
import argparse, csv, json, random, re, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent
CONTENT = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
RULES = json.loads((HERE / "rules.json").read_text(encoding="utf-8"))
PROMPTS_MD = (HERE / "prompts.md").read_text(encoding="utf-8")

SKILLS = {s["id"]: s for s in CONTENT["skills"]}
INTERESTS = {i["id"]: i for i in CONTENT["interests"]}
WORDS = [w for w in CONTENT["words"] if w["kind"] == "word"]
BLOCKLIST = [b.lower() for b in RULES["safety"]["blocklist"]]
JUDGMENTAL = [b.lower() for b in RULES["safety"]["judgmental_en"] + RULES["safety"]["judgmental_fil"]]
NEUTRAL_NAMES = RULES["personalization"]["neutral_distractor_names"]
FEELINGS = RULES["story_style"]["feeling_words_fil"]
SYLLABLES = {w["text"]: w["syllables"] for w in WORDS}
VOWELS = set("aeiou")

def syllabify(word):
    """Code splits syllables, not the model (small models split ng: bun-ga). Use content.json first; else
    the Filipino rule: ng is one letter; 1 consonant between vowels goes right (ba-hay), 2 split (bang-ka).
    Limit: loanword clusters (e-ro-pla-no, o-kra) need content.json or a tutor check."""
    if word in SYLLABLES:
        return SYLLABLES[word]
    t = re.findall(r"ng|.", word.lower())
    vi = [i for i, x in enumerate(t) if x in VOWELS]
    cuts = [a + 1 if b - a == 1 else (b - 1 if b - a == 2 else a + 2) for a, b in zip(vi, vi[1:])]
    out, prev = [], 0
    for c in cuts + [len(t)]:
        out.append("".join(t[prev:c]))
        prev = c
    return out
# Words that are English and never Filipino. ("at", "may", "bag", "basket" are not here: they are Filipino too.)
ENGLISH = set("""the and is are was were he she they his her him with of to in on for you your we our my
very happy sad play played playing go went home house park lunch drawing draw picture gift ball toy toys
rain umbrella mom dad okay yes so but then because birthday rocket friend friends school car truck
clap good job great nice try again vowel vowels sound letter letters word words""".split())

def english_words(text):
    # Split "I-clap" / "Pag-clap" so that Taglish is found too.
    return sorted({p.lower() for w in words_in(text) for p in w.split("-")} & ENGLISH)
# The mistake that goes with each weakest skill, for the words prompt.
SKILL_MISTAKE = {"sk_ng": "O_NG", "sk_cvc_final": "P_OMIT_FINAL", "sk_long_words": "S_SYLL_MISS",
                 "sk_cvc_mid": "P_OMIT_MID", "sk_clusters": "P_OMIT_MID", "sk_cvcv_1": "P_SUB_CONS",
                 "sk_vowels": "P_SUB_VOWEL", "sk_letters_1": "P_SUB_CONS"}
SETTINGS = ["bahay", "palengke", "ilog", "bukid", "kubo", "paaralan", "parke"]
WORD_RE = re.compile(r"[A-Za-zÑñ'-]+")

# Test learners: change these to test other cases.
LEARNERS = [
    {"child_id": "c_01", "name": "Ana", "level": 1, "interests": ["int_animals", "int_drawing"], "weakest": "sk_ng"},
    {"child_id": "c_02", "name": "Ben", "level": 1, "interests": ["int_basketball", "int_vehicles"], "weakest": "sk_cvc_final"},
    {"child_id": "c_03", "name": "Mila", "level": 2, "interests": ["int_food", "int_space"], "weakest": "sk_long_words"},
]
PATTERNS = {
    "sk_ng": "words that contain the letter ng",
    "sk_cvc_final": "words that end in a consonant",
    "sk_cvcv_1": "two-syllable words with only m, s, b, t, k and vowels",
    "sk_long_words": "words with three or more syllables",
    "sk_cvc_mid": "words with a closed syllable in the middle",
    "sk_clusters": "words with a consonant cluster such as pl, br, tr",
}

# ---------------------------------------------------------------- prompts.md parsing
def section(title_start):
    a = PROMPTS_MD.index(title_start)
    b = PROMPTS_MD.find("\n## ", a + 5)
    return PROMPTS_MD[a: b if b != -1 else None]

def code_after(text, label):
    i = text.index(label)
    a = text.index("```", i)
    a = text.index("\n", a) + 1
    b = text.index("```", a)
    return text[a:b].strip()

SYSTEM = code_after(section("## 1. Personal story"), "**System**")
TEMPLATES = {
    "story": code_after(section("## 1. Personal story"), "**User**"),
    "words": code_after(section("## 2. Practice words"), "**User**"),
    "feedback": code_after(section("## 3. Feedback"), "**User**"),
    "summary": code_after(section("## 4. Tutor summary"), "**User**"),
    "lesson": code_after(section("## 7. Mini lesson story"), "**User**"),
}

def fill(template, values):
    out = template
    for _ in range(2):  # twice: some values contain {name}
        for k, v in values.items():
            out = out.replace("{" + k + "}", str(v))
    left = sorted(set(re.findall(r"\{([a-z_0-9]+)\}", out)))
    return out, left

# ---------------------------------------------------------------- model call
GENERIC_SYSTEM = "Follow every rule. Output only valid JSON. No other text."

def clean_output(text):
    """Remove thinking blocks and code fences; keep the outer JSON object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = text.replace("\u2581", " ")              # tokenizer artifact (looks like ▁)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i != -1 and j > i else text

def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def call_model(model, user, temperature, num_predict, mock=None, system=GENERIC_SYSTEM,
               backend="lmstudio", base_url=None, schema=None, reasoning="none"):
    """Returns (cleaned text, seconds, finish) where finish is "length" if the output was cut off."""
    t0 = time.time()
    if mock is not None:
        return mock, time.time() - t0, "stop"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if backend == "ollama":
        url = (base_url or "http://localhost:11434") + "/api/chat"
        d = _post(url, {"model": model, "stream": False, "format": schema or "json", "keep_alive": "30m",
                        "messages": messages, "think": reasoning != "none",
                        "options": {"temperature": temperature, "num_predict": num_predict}})
        text = d["message"]["content"]
        finish = d.get("done_reason", "stop")
    else:  # LM Studio: OpenAI-compatible server
        url = (base_url or "http://localhost:1234") + "/v1/chat/completions"
        body = {"model": model, "messages": messages, "temperature": temperature,
                "max_tokens": num_predict, "stream": False,
                # Thinking models (Gemma 4) otherwise spend max_tokens on reasoning and return no content.
                "reasoning_effort": reasoning,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "output", "schema": schema or {"type": "object"}}}}
        try:
            d = _post(url, body)
        except urllib.error.HTTPError:
            body.pop("response_format")          # older LM Studio: no structured output
            d = _post(url, body)
        text = d["choices"][0]["message"]["content"] or ""
        finish = d["choices"][0].get("finish_reason", "stop")
    return clean_output(text), time.time() - t0, finish

def list_models(backend, base_url=None):
    if backend == "ollama":
        with urllib.request.urlopen((base_url or "http://localhost:11434") + "/api/tags") as r:
            return [m["name"] for m in json.loads(r.read())["models"]]
    with urllib.request.urlopen((base_url or "http://localhost:1234") + "/v1/models") as r:
        return [m["id"] for m in json.loads(r.read())["data"]]

# ---------------------------------------------------------------- helpers
def words_in(text):
    return WORD_RE.findall(text)

def sentences(text):
    # Split only when the next sentence starts with a capital or a quote, so that
    # '"Salamat!" sabi ni Lola.' stays one sentence.
    return [s for s in re.split(r'(?<=[.!?])["”]?\s+(?=[A-ZÑ"“])', text) if s.strip()]

def blocklisted(text):
    t = text.lower()
    return [b for b in BLOCKLIST if re.search(r"\b" + re.escape(b) + r"\b", t)]

def judgmental(text):
    t = text.lower()
    return [b for b in JUDGMENTAL if re.search(r"\b" + re.escape(b) + r"\b", t)]

def names_used(text):
    # In Filipino, person names follow the markers si, ni, kay, sina, nina (also at the start of a sentence).
    found = re.findall(r"\b(?:[Ss]i|[Nn]i|[Kk]ay|[Ss]ina|[Nn]ina)\s+([A-ZÑ][a-zñ]+)", text)
    return set(found)

PARTICLES = {"sa", "kay", "ang", "si", "ni", "ng", "na", "ay", "mga", "at", "nang", "ni", "nina", "sina"}
PREFIXES = ("nagpa", "nag", "mag", "pag", "nakaka", "naka", "maka", "na", "ma", "um", "in", "ka")

def stem(w):
    """Rough Filipino stem, so that nalungkot / malungkot / lungkot match each other."""
    w = w.lower().strip("'-")
    if w.endswith("ng") and len(w) > 5:              # linker: masayang -> masaya
        w = w[:-2]
    for p in PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 4:
            w = w[len(p):]
            break
    return w

def in_story(word, story_tokens):
    w, s = word.lower(), stem(word)
    for t in story_tokens:
        st = stem(t)
        if w == t or s == st or (len(s) >= 4 and s in st) or (len(st) >= 4 and st in s):
            return True
    return False

def object_regex(obj):
    # "laruang aso" may also be written "laruan na aso".
    words = obj.lower().split()
    parts = [re.escape(p[:-1]) + "(?:g| na)" if i < len(words) - 1 and len(p) > 4 and p.endswith("ng")
             else re.escape(p) for i, p in enumerate(words)]
    return re.compile(r"\b" + r"\s+".join(parts))

def has_object(text, obj, head_ok=False):
    t = text.lower()
    if object_regex(obj).search(t):
        return True
    head = obj.lower().split()[-1]
    return head_ok and in_story(head, [x.lower() for x in words_in(text)])

# ---------------------------------------------------------------- checks
def check_story(out, v, learner):
    fails = []
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    for k in ("title", "paragraphs", "questions"):
        if k not in d:
            fails.append("missing_" + k)
    if fails:
        return fails, d
    paras = d["paragraphs"] if isinstance(d["paragraphs"], list) else [str(d["paragraphs"])]
    paras = [str(p) for p in paras]
    text = " ".join(paras)
    tokens = [w.lower() for w in words_in(text)]
    lv = RULES["story_levels"][str(learner["level"])]
    if len(paras) != lv["paragraphs"]:
        fails.append(f"paragraph_count_{len(paras)}")
    n = len(tokens)
    if not (lv["min_words"] <= n <= lv["max_words"]):
        fails.append(f"word_count_{n}")
    sents = sentences(text)
    lo, hi = v["_sent_range"]
    if not (lo <= len(sents) <= hi):
        fails.append(f"sentence_count_{len(sents)}")
    long_s = [x for x in sents if len(words_in(x)) > lv["max_words_per_sentence"]]
    if long_s:
        fails.append(f"long_sentences_{len(long_s)}")
    if sents and words_in(sents[-1]) and words_in(sents[-1])[0].lower() == "sana":
        fails.append("ends_with_sana")
    if len(re.findall(r"\b" + re.escape(learner["name"]) + r"\b", text)) < RULES["personalization"]["personal_story"]["min_name_mentions"]:
        fails.append("name_under_2")
    # Review r4: "Umuwi sila nang masaya, si Ana." - the name added at the end only to reach the count.
    if re.search(r",\s*(?:si|ni|kay)\s+" + re.escape(learner["name"]) + r"\s*[.!?]", text, re.I):
        fails.append("name_tacked_on")
    # rules.md 9: the object matters in the first and the last beat. The full phrase is in the first
    # paragraph; later, the head noun is enough ("laruang aso" ... "aso").
    if not has_object(paras[0], v["object"]):
        fails.append("object_not_in_first")
    if not has_object(paras[-1], v["object"], head_ok=True):
        fails.append("object_not_in_last")
    allowed = {learner["name"], *v["_other_names_list"]}
    extra = names_used(text) - allowed
    if extra:
        fails.append("other_names_" + "_".join(sorted(extra)))
    english = english_words(text + " " + str(d.get("title", "")))
    qs = d.get("questions", [])
    if len(qs) != 3:
        fails.append(f"questions_{len(qs)}")
    # The same types that code chose (Level 2: sequence and feeling are required). The order does not matter.
    if sorted(str(q.get("type", "")).lower().strip() for q in qs) != sorted(v["_qtypes"]):
        fails.append("question_types_wrong")
    name_ok = {x.lower() for x in allowed | set(NEUTRAL_NAMES)}
    for q in qs:
        ch = [str(x) for x in q.get("choices", [])]
        ans = str(q.get("answer", ""))
        qtype = str(q.get("type", "")).lower().strip()
        english += english_words(" ".join(ch) + " " + str(q.get("prompt", "")))
        if len(ch) != 3 or len(set(c.lower().strip() for c in ch)) != 3 or ans not in ch:
            fails.append("bad_choices")
        if qtype not in lv["question_types"]:
            fails.append("bad_question_type")
        if qtype == "who":
            # rules.md 9: wrong *name* choices come only from neutral_distractor_names, never other children.
            # Common nouns ("ang tindera") are not names; only capitalized words are checked.
            for c in ch:
                for w in words_in(c):
                    if w[0].isupper() and w.lower() not in PARTICLES and w.lower() not in name_ok:
                        fails.append("who_choice_not_allowed_" + w)
        # Review r4: a where answer "nawala" and a feeling answer "maingat" passed.
        if qtype == "where" and not re.match(r"(?:sa|nasa)\s", ans.strip().lower()):
            fails.append("where_not_a_place")
        if qtype == "feeling" and not any(in_story(w, FEELINGS) for w in words_in(ans.lower())):
            fails.append("feeling_not_a_feeling_word")
        if qtype in ("who", "what", "where", "feeling"):
            content = [w for w in words_in(ans.lower()) if w not in PARTICLES]
            found = [w for w in content if in_story(w, tokens)]
            if not content or len(found) * 2 < len(content):      # less than half of the answer words
                fails.append("answer_not_in_story")
    if english:
        fails.append("english_" + "_".join(sorted(set(english))))
    bl = blocklisted(json.dumps(d, ensure_ascii=False))
    if bl:
        fails.append("blocklist_" + "_".join(bl))
    return list(dict.fromkeys(fails)), d

def check_words(out, v):
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    fails = []
    ws = d.get("words", [])
    if len(ws) != v["count"]:
        fails.append(f"count_{len(ws)}")
    texts = [str(w.get("text")) for w in ws]
    if len(set(texts)) != len(texts):
        fails.append("duplicate_words")
    # The model only selects. Code adds the syllables (syllabify), the tiles, and the distractor tiles.
    for t in texts:
        if t not in v["_candidates"]:
            fails.append("not_in_candidates_" + t)
    if blocklisted(json.dumps(d, ensure_ascii=False)):
        fails.append("blocklist")
    return fails, d

def check_feedback(out, v):
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    fails = []
    for k in ("message_fil", "hint_fil"):
        if len(words_in(str(d.get(k, "")))) > 12:
            fails.append("too_long_" + k)
    for k in ("message_fil", "hint_fil"):
        if not str(d.get(k, "")).strip():
            fails.append("empty_" + k)
    body = " ".join(str(d.get(k, "")) for k in ("message_fil", "hint_fil"))
    # "ba-hay", "ba hay" and "b-a-h-a-y" also give the answer away.
    joined = re.sub(r"[\s\-·.,]+", "", body.lower())
    if int(v["attempt"]) < 3 and v["expected"].lower() in joined:
        fails.append("gives_answer_early")
    english = english_words(body)
    if english:
        fails.append("english_" + "_".join(english))
    if blocklisted(body):
        fails.append("blocklist")
    if judgmental(body):
        fails.append("judgmental_" + "_".join(judgmental(body)))
    return fails, d

def check_summary(out, v):
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    fails = []
    got = {x.get("child_id") for x in d.get("learners", [])}
    if got != set(v["_stats"].keys()):
        fails.append("child_ids_mismatch")
    for x in d.get("learners", []):
        st = v["_stats"].get(x.get("child_id"))
        if x.get("next_focus_skill") not in SKILLS:
            fails.append("bad_skill_id")
        if x.get("next_method") not in RULES["methods"]:
            fails.append("bad_method")
        summ = str(x.get("summary", ""))
        if len(summ.split()) > 25:                     # words between spaces ("sk_cvc_final" is one word)
            fails.append("summary_too_long")
        # The tutor reads this: plain words, not ids such as P_SUB_VOWEL or sk_ng (see the example output).
        if re.search(r"\b(?:sk_\w+|[A-Z]+_[A-Z_]+)\b|\b(?:" + "|".join(RULES["methods"]) + r")\b", summ):
            fails.append("ids_in_summary")
        if st and f'{st["correct"]} of {st["total"]}' not in x.get("summary", ""):
            fails.append("numbers_mismatch")
        if "%" in x.get("summary", ""):
            fails.append("percentage")
    # prompts.md 4: if 2 or more learners have the same main mistake, write a note to the tutor.
    if v["_shared_mistake"] and not str(d.get("group_note", "")).strip():
        fails.append("group_note_missing")
    text = json.dumps(d, ensure_ascii=False)
    for bad in judgmental(text):
        fails.append("judgmental_" + bad)
    if blocklisted(text):
        fails.append("blocklist")
    return list(dict.fromkeys(fails)), d

# ---------------------------------------------------------------- test case builders
def pick_question_types(lv, rnd):
    n = RULES["story_style"]["questions_per_story"]
    required = list(lv["required_question_types"])
    rest = [t for t in lv["question_types"] if t not in required]
    rnd.shuffle(rest)
    return (required + rest)[:n]

def numbered_beats(beats, name, obj):
    return "\n".join(f"Paragraph {i}: " + b.replace("{name}", name).replace("{object}", obj)
                     for i, b in enumerate(beats, 1))

def story_schema(paragraphs, qtypes):
    nq, nc = RULES["story_style"]["questions_per_story"], RULES["story_style"]["choices_per_question"]
    s = {"type": "string"}
    return {"type": "object", "required": ["title", "paragraphs", "questions"], "properties": {
        "title": s,
        "paragraphs": {"type": "array", "items": s, "minItems": paragraphs, "maxItems": paragraphs},
        "questions": {"type": "array", "minItems": nq, "maxItems": nq, "items": {
            "type": "object", "required": ["type", "prompt", "choices", "answer"], "properties": {
                "type": {"type": "string", "enum": qtypes},
                "prompt": s,
                "choices": {"type": "array", "items": s, "minItems": nc, "maxItems": nc},
                "answer": s}}}}}

def interest_of(learner, obj):
    """The learner's interest (English label, lower case) that the object comes from, for the prompt."""
    for i in learner.get("interests") or []:
        if obj in INTERESTS[i]["objects"]:
            return INTERESTS[i]["label_en"].lower()
    ids = learner.get("interests") or []
    return INTERESTS[ids[0]]["label_en"].lower() if ids else "playing"

def story_case(learner, rnd):
    lv = RULES["story_levels"][str(learner["level"])]
    # Each plot lists the objects that fit it (no shoes to play with at the park, no crayons in the rain).
    # Choose a plot that fits one of the learner's interest objects, then an object that fits the plot.
    mine = [o for i in learner["interests"] for o in INTERESTS[i]["objects"]]
    at_level = [p for p in CONTENT["story_plots"] if p["level"] == learner["level"]]
    plots = [p for p in at_level if set(p["fits_objects"]) & set(mine)]
    if plots:
        plot = rnd.choice(plots)
        obj = rnd.choice([o for o in mine if o in plot["fits_objects"]])
    else:   # no plot fits the learner's objects: any plot at the level, with an object that fits it
        plot = rnd.choice(at_level)
        obj = rnd.choice(plot["fits_objects"])
    plot_text = plot["outline_en"].replace("{name}", learner["name"]).replace("{object}", obj)
    skill_words = [w["text"] for w in WORDS if learner["weakest"] in w["skill_ids"]]
    optional = rnd.sample(skill_words, 2)
    ex = CONTENT["story_examples"][str(learner["level"])]
    lo, hi = lv["min_sentences"], lv["max_sentences"]
    wlo, whi = lv["target_words_per_sentence"]
    qtypes = pick_question_types(lv, rnd)
    v = {
        "name": learner["name"], "object": obj, "plot": plot_text, "interest": interest_of(learner, obj),
        "beats": numbered_beats(plot["beats_en"], learner["name"], obj),
        "word_bank": ", ".join(plot["word_bank_fil"]),
        "connectors": ", ".join(RULES["story_style"]["connectors_fil"]),
        "other_names": ", ".join(plot["characters"]), "level": learner["level"],
        "distractor_names": ", ".join(NEUTRAL_NAMES), "feeling_words": ", ".join(FEELINGS),
        "paragraphs": lv["paragraphs"], "sentences_per_paragraph": lv["sentences_per_paragraph"],
        "min_wps": wlo, "max_wps": whi,
        "min_words": lv["min_words"], "max_words": lv["max_words"],
        "max_words_per_sentence": lv["max_words_per_sentence"], "question_types": ", ".join(qtypes),
        "optional_words": ", ".join(optional),
        "example_name": ex["name"], "example_object": ex["object"],
        "example_other_names": ", ".join(ex["characters"]),
        "example_beats": numbered_beats(ex["beats_en"], ex["name"], ex["object"]),
        "example_json": json.dumps(ex["output"], ensure_ascii=False),
        "_other_names_list": plot["characters"], "_optional": optional, "_plot_id": plot["id"],
        "_sent_range": (lo, hi), "_schema": story_schema(lv["paragraphs"], qtypes), "_qtypes": qtypes,
    }
    return v

def words_case(learner, rnd):
    sk = learner["weakest"]
    cands = [w["text"] for w in WORDS if sk in w["skill_ids"]] or [w["text"] for w in WORDS][:20]
    return {"count": min(5, len(cands)), "skill_name_en": SKILLS[sk]["name_en"],
            "pattern_description": PATTERNS.get(sk, SKILLS[sk]["name_en"]),
            "mistake_description": RULES["mistake_types"][SKILL_MISTAKE.get(sk, "P_OMIT_FINAL")]["description_en"],
            "candidate_words": ", ".join(cands), "_candidates": set(cands),
            "_schema": words_schema(cands, min(5, len(cands)))}

def words_schema(cands, count):
    # Like the story schema: the model can only output candidate words, and exactly `count` of them.
    return {"type": "object", "required": ["words"], "properties": {"words": {
        "type": "array", "minItems": count, "maxItems": count, "items": {
            "type": "object", "required": ["text", "meaning_en"], "properties": {
                "text": {"type": "string", "enum": list(cands)}, "meaning_en": {"type": "string"}}}}}}

def feedback_case(learner, rnd):
    code = rnd.choice(["P_OMIT_FINAL", "P_SUB_VOWEL", "O_NG", "S_SYLL_MISS"])
    ex = {"P_OMIT_FINAL": ("bahay", "baha"), "P_SUB_VOWEL": ("mesa", "misa"),
          "O_NG": ("ngipin", "nipin"), "S_SYLL_MISS": ("sapatos", "sapos")}[code]
    m = RULES["mistake_types"][code]
    return {"name": learner["name"], "task_type": "dictation_letters", "expected": ex[0], "given": ex[1],
            "mistake_description": m["description_en"],
            "method_description": RULES["methods"][m["method"]]["description_en"],
            "attempt": rnd.choice([1, 2]), "support_level": "guide"}

def summary_case(rnd):
    stats, lines, main = {}, [], []
    for L in LEARNERS:
        total = 10
        correct = rnd.randint(3, 9)
        mis = rnd.choice(["O_NG", "P_OMIT_FINAL", "P_SUB_VOWEL"])
        main.append(mis)
        stats[L["child_id"]] = {"correct": correct, "total": total}
        # Codes go with their meaning, or the model guesses what O_NG means and writes wrong facts.
        sk = f'{L["weakest"]} ({SKILLS[L["weakest"]]["name_en"]})'
        lines.append(f'{L["child_id"]} | {L["name"]} | {correct} of {total} correct | skills: {sk} | '
                     f'weakest: {sk} | mistakes: {mis} ({RULES["mistake_types"][mis]["description_en"]}) '
                     f'x{rnd.randint(2, 4)} | support: guide | alert: no')
    return {"date": "2026-10-12", "present_count": len(LEARNERS), "learner_data": "\n".join(lines),
            "method_list": ", ".join(RULES["methods"].keys()),
            "skill_list": ", ".join(f'{s["id"]} ({s["name_en"]})' for s in CONTENT["skills"]), "_stats": stats,
            "_shared_mistake": len(set(main)) < len(main)}

# ---------------------------------------------------------------- mock outputs (for --mock)
def lesson_case(learner, rnd):
    """The mini lesson story (prompts.md section 7): 2 words of the skill, an object from the interests."""
    sk = learner.get("lesson_skill") or learner["weakest"]
    words = [w["text"] for w in WORDS if sk in w["skill_ids"]]
    lesson_words = rnd.sample(words, min(2, len(words)))
    objects = [o for i in learner["interests"] for o in INTERESTS[i]["objects"]] if learner.get("interests") else []
    obj = rnd.choice(objects) if objects else "bola"
    s = {"type": "string"}
    return {"name": learner["name"], "object": obj, "interest": interest_of(learner, obj),
            "skill_name_en": SKILLS[sk]["name_en"],
            "pattern_description": PATTERNS.get(sk, SKILLS[sk]["name_en"]), "lesson_words": ", ".join(lesson_words),
            "_words": lesson_words, "_skill": sk,
            "_schema": {"type": "object", "required": ["sentences"], "properties": {
                "sentences": {"type": "array", "minItems": 3, "maxItems": 3, "items": s}}}}


def check_lesson(out, v, learner):
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    sents = d.get("sentences") if isinstance(d, dict) else None
    if not isinstance(sents, list) or len(sents) != 3:
        return [f"sentences_{len(sents) if isinstance(sents, list) else 0}"], d
    fails = []
    text = " ".join(str(x) for x in sents)
    tokens = [w.lower() for w in words_in(text)]
    if any(not (4 <= len(words_in(str(x))) <= 8) for x in sents):
        fails.append("sentence_length")
    if not re.search(r"\b" + re.escape(v["name"]) + r"\b", text):
        fails.append("name_missing")
    if not has_object(text, v["object"], head_ok=True):
        fails.append("object_missing")
    missing = [w for w in v["_words"] if w.lower() not in tokens]
    if missing:
        fails.append("lesson_words_missing_" + "_".join(missing))
    extra = names_used(text) - {v["name"]}
    if extra:
        fails.append("other_names_" + "_".join(sorted(extra)))
    english = english_words(text)
    if english:
        fails.append("english_" + "_".join(english))
    if blocklisted(text):
        fails.append("blocklist")
    return fails, d


def mock_output(kind, v, learner):
    if kind == "story":
        n, o = learner["name"], v["object"]
        oth = v["_other_names_list"][0]
        paras = [f"Umaga na at maaraw sa labas. Dinala ni {n} ang {o}. Nakita niya si {oth} doon.",
                 f"Kaya sabay silang naglaro ng {o}. Tumawa sila nang malakas. Masaya sila sa labas.",
                 f"Pagkatapos, umuwi na sila sa bahay. Dala ni {n} ang {o}. Masaya si {n} sa araw na ito."]
        if learner["level"] == 2:
            paras = [f"Umaga na at maaraw sa labas ng bahay. Dinala ni {n} ang {o} sa bakuran. Nakita niya roon si {oth} na nagwawalis.",
                     f"Kaya tinulungan niya si {oth} sa paglilinis ng bakuran. Pagkatapos, sabay silang naglaro ng {o}. Tumawa sila nang malakas at masaya.",
                     f"Pagdating sa bahay, nagluto si {oth} ng tanghalian. Habang naghihintay, naglaro ulit si {n} ng {o}. Sabay silang kumain nang masaya."]
        oth_choice = "Kuya" if oth != "Kuya" else "Ate"
        qs = {"who": ("Sino ang may " + o + "?", [n, "Lola" if oth != "Lola" else "Lolo", oth_choice], n),
              "what": ("Ano ang dinala ni " + n + "?", [o, "kutsara", "unan"], o),
              "where": ("Saan sila umuwi?", ["sa bahay", "sa ilog", "sa bukid"], "sa bahay"),
              "feeling": ("Ano ang naramdaman ni " + n + "?", ["masaya", "malungkot", "galit"], "masaya"),
              "sequence": ("Ano ang unang nangyari?", [f"Dinala ni {n} ang {o}.", "Kumain sila.", "Umuwi sila."],
                           f"Dinala ni {n} ang {o}."),
              "main_idea": ("Tungkol saan ang kuwento?", [f"Ang {o} ni {n}", "Ang ulan", "Ang ilog"], f"Ang {o} ni {n}")}
        return json.dumps({"title": "Test", "paragraphs": paras,
                           "questions": [{"type": t, "prompt": qs[t][0], "choices": qs[t][1], "answer": qs[t][2]}
                                         for t in v["_qtypes"]]}, ensure_ascii=False)
    if kind == "words":
        c = sorted(v["_candidates"])[: v["count"]]
        return json.dumps({"words": [{"text": w, "meaning_en": ""} for w in c]})
    if kind == "feedback":
        return json.dumps({"message_fil": "Malapit na!", "hint_fil": "Pakinggan ulit ang salita."})
    if kind == "lesson":
        a, b = (v["_words"] + v["_words"])[:2]
        return json.dumps({"sentences": [f"Si {v['name']} ay may {v['object']} sa bahay.",
                                         f"Nakita niya ang {a} at {b} doon.",
                                         f"Masaya siya sa {a} at {b}."]}, ensure_ascii=False)
    st = v["_stats"]
    return json.dumps({"learners": [{"child_id": k, "summary": f'{s["correct"]} of {s["total"]} correct.',
                                     "next_focus_skill": "sk_ng", "next_method": "ng_sound_pairs"} for k, s in st.items()],
                       "group_note": "Two learners share a mistake." if v["_shared_mistake"] else ""})

# ---------------------------------------------------------------- self-test (runs with --mock)
def example_case(level):
    ex = CONTENT["story_examples"][str(level)]
    lv = RULES["story_levels"][str(level)]
    v = {"object": ex["object"], "_other_names_list": ex["characters"],
         "_sent_range": (lv["min_sentences"], lv["max_sentences"]),
         "_qtypes": [q["type"] for q in ex["output"]["questions"]]}
    return ex, v, {"name": ex["name"], "level": level}

def selftest():
    """The examples must pass (rules.md 10), and known-bad outputs must fail with the right label."""
    problems = []
    # The story check wants the object in the first and the last paragraph, so every plot must have it
    # in its first and last beat, and one beat per paragraph.
    for pl in CONTENT["story_plots"]:
        if "{object}" not in pl["beats_en"][0] or "{object}" not in pl["beats_en"][-1]:
            problems.append(f"{pl['id']}: the object is not in the first and the last beat")
        if len(pl["beats_en"]) != RULES["story_levels"][str(pl["level"])]["paragraphs"]:
            problems.append(f"{pl['id']}: {len(pl['beats_en'])} beats, but the level has a different paragraph count")
    for level in (1, 2):
        ex, v, L = example_case(level)
        fails, _ = check_story(json.dumps(ex["output"], ensure_ascii=False), v, L)
        if fails:
            problems.append(f"example level {level} fails: {fails}")
    ex, v, L = example_case(1)
    def bad(change, label):
        d = json.loads(json.dumps(ex["output"]))
        change(d)
        fails, _ = check_story(json.dumps(d, ensure_ascii=False), v, L)
        if not any(f.startswith(label) for f in fails):
            problems.append(f"expected {label}, got {fails}")
    bad(lambda d: d["paragraphs"].__setitem__(1, d["paragraphs"][1] + " Sumama si Maria."), "other_names_Maria")
    bad(lambda d: d["paragraphs"].__setitem__(0, "Si Maria ay " + d["paragraphs"][0]), "other_names_Maria")
    bad(lambda d: d["paragraphs"].__setitem__(1, "Agad niya itong dinala kay Lola. Sabay silang umuwi nang tuyo. \"Salamat, Carlo!\" sabi ni Lola."), "object_not_in_last")
    bad(lambda d: d["questions"][0].__setitem__("choices", ["Lola", "Ben", "Tatay"]), "who_choice_not_allowed_Ben")
    bad(lambda d: d["questions"][2].__setitem__("type", "who"), "question_types_wrong")   # where -> who
    bad(lambda d: d["paragraphs"].__setitem__(1, d["paragraphs"][1] + " Sana masaya tayo."), "ends_with_sana")
    # Multi-word object: full phrase (or "laruan na aso") first, head noun is enough at the end.
    for first, last, ok in [("Dinala ni Ana ang laruang aso.", "Masaya ang aso.", True),
                            ("Dinala ni Ana ang laruan na aso.", "Niyakap niya ang kanyang aso.", True),
                            ("Dinala ni Ana ang aso.", "Masaya ang aso.", False)]:
        got = has_object(first, "laruang aso") and has_object(last, "laruang aso", head_ok=True)
        if got != ok:
            problems.append(f"object check wrong for {first!r} / {last!r}")
    bad(lambda d: d["paragraphs"].__setitem__(0, d["paragraphs"][0] + " Masaya ang lunch."), "english_lunch")
    bad(lambda d: d["questions"][1].__setitem__("answer", "aklat"), "answer_not_in_story")
    fails, _ = check_words(json.dumps({"words": [{"text": "ulan"}]}), {"count": 1, "_candidates": {"bahay"}})
    if "not_in_candidates_ulan" not in fails:
        problems.append(f"words: invented word passed: {fails}")
    # The syllable rule (without content.json) must agree with content.json, except loanword clusters.
    saved = dict(SYLLABLES)
    SYLLABLES.clear()
    try:
        wrong = [t for t, s in saved.items() if syllabify(t) != s and t not in ("eroplano", "okra")]
    finally:
        SYLLABLES.update(saved)
    if wrong:
        problems.append(f"syllabify disagrees with content.json: {wrong}")
    fails, _ = check_feedback(json.dumps({"message_fil": "Malapit na!", "hint_fil": "Pakinggan: ba-hay."}),
                              {"attempt": 1, "expected": "bahay"})
    if "gives_answer_early" not in fails:
        problems.append(f"feedback: hyphenated answer passed: {fails}")
    fails, _ = check_feedback(json.dumps({"message_fil": "Mabagal ka.", "hint_fil": "Subukan ulit."}),
                              {"attempt": 1, "expected": "bahay"})
    if not any(f.startswith("judgmental") for f in fails):
        problems.append(f"feedback: judgmental passed: {fails}")
    # Mini lesson story: the mock passes; a missing lesson word and an extra name fail.
    lv = lesson_case(dict(LEARNERS[0]), random.Random(1))
    fails, _ = check_lesson(mock_output("lesson", lv, LEARNERS[0]), lv, LEARNERS[0])
    if fails:
        problems.append(f"lesson mock fails: {fails}")
    bad_lesson = json.dumps({"sentences": [f"Si {lv['name']} ay may {lv['object']} dito.", "Sumama si Maria sa bahay.",
                                           "Masaya sila sa bahay ngayon."]})
    fails, _ = check_lesson(bad_lesson, lv, LEARNERS[0])
    if not any(f.startswith("lesson_words_missing") for f in fails) or "other_names_Maria" not in fails:
        problems.append(f"lesson: bad story passed: {fails}")
    print("Self-test:", "PASS" if not problems else "FAIL")
    for p in problems:
        print("  -", p)
    return not problems

# ---------------------------------------------------------------- main
SETTINGS_BY_KIND = {"story": (0.5, 600), "words": (0.3, 300), "feedback": (0.4, 120), "summary": (0.3, 400),
                    "lesson": (0.5, 200)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="default: gemma4:e4b (Ollama), google/gemma-4-e4b (LM Studio)")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--prompt", default="all", choices=["all", "story", "words", "feedback", "summary", "lesson"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--backend", default="ollama", choices=["ollama", "lmstudio"])
    ap.add_argument("--base-url", default=None, help="default: http://localhost:1234 (LM Studio) or :11434 (Ollama)")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--tag", default="", help="added to the output file names, for example the model name")
    ap.add_argument("--no-retry", action="store_true", help="do not retry a failed check (no pass@2)")
    ap.add_argument("--reasoning", default="none", help="reasoning effort for thinking models (none/low/medium/high)")
    a = ap.parse_args()
    if a.model is None:
        a.model = "mock" if a.mock else {"ollama": "gemma4:e4b", "lmstudio": "google/gemma-4-e4b"}[a.backend]
    if a.mock and not selftest():
        raise SystemExit(1)
    if a.list_models:
        for m in list_models(a.backend, a.base_url):
            print(m)
        return
    rnd = random.Random(a.seed)
    kinds = ["story", "words", "feedback", "summary", "lesson"] if a.prompt == "all" else [a.prompt]

    rows, review = [], []
    for kind in kinds:
        for i in range(a.runs):
            learner = LEARNERS[i % len(LEARNERS)]
            v = {"story": lambda: story_case(learner, rnd), "words": lambda: words_case(learner, rnd),
                 "feedback": lambda: feedback_case(learner, rnd), "summary": lambda: summary_case(rnd),
                 "lesson": lambda: lesson_case(learner, rnd)}[kind]()
            prompt, unfilled = fill(TEMPLATES[kind], {k: x for k, x in v.items() if not k.startswith("_")})
            temp, num = SETTINGS_BY_KIND[kind]

            def run_once():
                out, err = None, None
                for _ in range(2):                       # retry once on a server error
                    try:
                        out, secs, finish = call_model(a.model, prompt, temp, num,
                                                       mock=mock_output(kind, v, learner) if a.mock else None,
                                                       system=SYSTEM if kind == "story" else GENERIC_SYSTEM,
                                                       backend=a.backend, base_url=a.base_url,
                                                       schema=v.get("_schema"), reasoning=a.reasoning)
                        break
                    except Exception as e:
                        err = e
                        time.sleep(3)
                if out is None:
                    return None, 0.0, [f"error_{err}"], None
                fails, parsed = {"story": lambda: check_story(out, v, learner), "words": lambda: check_words(out, v),
                                 "feedback": lambda: check_feedback(out, v),
                                 "summary": lambda: check_summary(out, v),
                                 "lesson": lambda: check_lesson(out, v, learner)}[kind]()
                if finish == "length":
                    fails.insert(0, "truncated")
                if unfilled:
                    fails.append("unfilled_placeholders_" + "_".join(unfilled))
                return out, secs, fails, parsed

            out, secs, fails, parsed = run_once()
            ok = "PASS" if not fails else ("ERROR" if out is None else "FAIL")
            # The app retries once with the same prompt after a failed check (prompts.md 0): pass@2.
            ok2, fails2 = ok, []
            if ok != "PASS" and not a.no_retry:
                out2, secs2, fails2, parsed2 = run_once()
                ok2 = "PASS" if not fails2 else "FAIL"
                if kind == "story" and parsed2:
                    review.append((f"{i + 1}b", learner, parsed2, ok2, fails2, v["plot"]))
            rows.append([kind, a.model, i + 1, learner["name"], ok, ";".join(fails), f"{secs:.1f}", out, ok2,
                         ";".join(fails2)])
            retry = f"  | retry {ok2} {';'.join(fails2)}" if fails2 or (ok != "PASS" and not a.no_retry) else ""
            print(f"{kind:8s} #{i+1:<2} {learner['name']:5s} {ok}  {secs:5.1f}s  {';'.join(fails)}{retry}")
            if kind == "story" and parsed:
                review.append((i + 1, learner, parsed, ok, fails, v["plot"]))

    tag = "_" + re.sub(r"[^A-Za-z0-9._-]+", "-", a.tag or a.model) if (a.tag or not a.mock) else ""
    res_path, rev_path = HERE / f"results{tag}.csv", HERE / f"stories_for_review{tag}.md"
    with open(res_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prompt", "model", "run", "learner", "result", "failed_checks", "seconds", "output",
                    "result_after_retry", "retry_failed_checks"])
        w.writerows(rows)

    md = [f"# Stories for review ({a.model})\n",
          "Rate each story 1-5 for **makes sense**, **natural Filipino**, and **child safety**. Compare it with its plot.\n"]
    for n, L, d, ok, fails, pl in review:
        md.append(f"## Run {n}: {L['name']} (Level {L['level']}) - checks: {ok}")
        md.append(f"Plot: {pl}\n")
        if fails:
            md.append(f"Failed checks: {', '.join(fails)}\n")
        md.append(f"**{d.get('title', '')}**\n")
        paras = d.get("paragraphs", [])
        md += [str(p) + "\n" for p in (paras if isinstance(paras, list) else [paras])]
        for q in d.get("questions", []):
            md.append(f"- ({q.get('type')}) {q.get('prompt')} - {' / '.join(map(str, q.get('choices', [])))} - answer: {q.get('answer')}")
        md.append("\nMakes sense (1-5): ____   Natural Filipino (1-5): ____   Child safety (1-5): ____   Notes: ____________\n")
    rev_path.write_text("\n".join(md), encoding="utf-8")

    print("\nSummary")
    for kind in kinds:
        rs = [r for r in rows if r[0] == kind]
        passed = sum(r[4] == "PASS" for r in rs)
        passed2 = sum(r[8] == "PASS" for r in rs)
        secs = [float(r[6]) for r in rs if r[6]]
        avg = sum(secs) / len(secs) if secs else 0
        print(f"  {kind:8s} pass@1 {passed}/{len(rs)}   pass@2 {passed2}/{len(rs)}   avg {avg:.1f}s")
    print(f"Saved {res_path.name} and {rev_path.name}")

if __name__ == "__main__":
    main()
