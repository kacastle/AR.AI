#!/usr/bin/env python3
"""
Prompt test harness for Reading Tutor PH.

Reads the prompts directly from prompts.md, fills them with test learners,
calls the local Ollama model, runs the checks from prompts.md, and saves:
  - results.csv              one row per run (pass/fail, failed checks, seconds)
  - stories_for_review.md    every story, for the Filipino speaker to rate 1-5

Usage (from the folder with content.json, rules.json, prompts.md):
  LM Studio (start the local server in LM Studio first):
    python test_prompts.py --backend lmstudio --list-models
    python test_prompts.py --backend lmstudio --model <model-id> --runs 10
  Ollama:
    python test_prompts.py --backend ollama --model <model-name> --runs 10
  One prompt only:
    python test_prompts.py --backend lmstudio --model <model-id> --prompt story --runs 5
  No model (checks this script):
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
NEUTRAL_NAMES = RULES["personalization"]["neutral_distractor_names"]
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
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if i != -1 and j > i else text

def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def call_model(model, user, temperature, num_predict, mock=None, system=GENERIC_SYSTEM,
               backend="lmstudio", base_url=None):
    t0 = time.time()
    if mock is not None:
        return mock, time.time() - t0
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if backend == "ollama":
        url = (base_url or "http://localhost:11434") + "/api/chat"
        d = _post(url, {"model": model, "stream": False, "format": "json", "keep_alive": "30m",
                        "messages": messages,
                        "options": {"temperature": temperature, "num_predict": num_predict}})
        text = d["message"]["content"]
    else:  # LM Studio: OpenAI-compatible server
        url = (base_url or "http://localhost:1234") + "/v1/chat/completions"
        body = {"model": model, "messages": messages, "temperature": temperature,
                "max_tokens": num_predict, "stream": False,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "output", "schema": {"type": "object"}}}}
        try:
            d = _post(url, body)
        except urllib.error.HTTPError:
            body.pop("response_format")          # older LM Studio: no structured output
            d = _post(url, body)
        text = d["choices"][0]["message"]["content"] or ""
    return clean_output(text), time.time() - t0

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
    return [s for s in re.split(r'(?<=[.!?])["”]?\s+', text) if s.strip()]

def blocklisted(text):
    t = text.lower()
    return [b for b in BLOCKLIST if re.search(r"\b" + re.escape(b) + r"\b", t)]

def names_used(text):
    # In Filipino, person names follow the markers si, ni, kay, sina, nina.
    found = re.findall(r"\b(?:si|ni|kay|sina|nina)\s+([A-ZÑ][a-zñ]+)", text)
    return set(found)

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
    text = " ".join(d["paragraphs"]) if isinstance(d["paragraphs"], list) else str(d["paragraphs"])
    low = text.lower()
    lv = RULES["story_levels"][str(learner["level"])]
    n = len(words_in(text))
    if not (lv["min_words"] <= n <= lv["max_words"]):
        fails.append(f"word_count_{n}")
    sents = sentences(text)
    lo, hi = v["_sent_range"]
    if not (lo <= len(sents) <= hi):
        fails.append(f"sentence_count_{len(sents)}")
    long_s = [x for x in sents if len(words_in(x)) > lv["max_words_per_sentence"]]
    if long_s:
        fails.append(f"long_sentences_{len(long_s)}")
    if len(re.findall(r"\b" + re.escape(learner["name"]) + r"\b", text)) < RULES["personalization"]["personal_story"]["min_name_mentions"]:
        fails.append("name_under_2")
    if v["object"].lower() not in low:
        fails.append("object_missing")
    allowed = {learner["name"], *v["_other_names_list"]}
    extra = names_used(text) - allowed
    if extra:
        fails.append("other_names_" + "_".join(sorted(extra)))
    qs = d.get("questions", [])
    if len(qs) != 3:
        fails.append(f"questions_{len(qs)}")
    for q in qs:
        ch = [str(x) for x in q.get("choices", [])]
        ans = str(q.get("answer", ""))
        if ans not in ch or len(set(ch)) != 3:
            fails.append("bad_question")
        if q.get("type") not in lv["question_types"]:
            fails.append("bad_question_type")
        if q.get("type") in ("who", "what", "where"):
            core = re.sub(r"^(sa|kay|ang|si|ni)\s+", "", ans.lower()).strip(" .!?")
            if core and core not in low:
                fails.append("answer_not_in_story")
    bl = blocklisted(json.dumps(d, ensure_ascii=False))
    if bl:
        fails.append("blocklist_" + "_".join(bl))
    return fails, d

def check_words(out, v):
    try:
        d = json.loads(out)
    except Exception:
        return ["json_parse"], None
    fails = []
    ws = d.get("words", [])
    if len(ws) != v["count"]:
        fails.append(f"count_{len(ws)}")
    for w in ws:
        if w.get("text") not in v["_candidates"]:
            fails.append("not_in_candidates_" + str(w.get("text")))
        if "".join(w.get("syllables", [])) != w.get("text"):
            fails.append("bad_syllables_" + str(w.get("text")))
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
    if int(v["attempt"]) < 3 and v["expected"].lower() in json.dumps(d, ensure_ascii=False).lower():
        fails.append("gives_answer_early")
    if blocklisted(json.dumps(d, ensure_ascii=False)):
        fails.append("blocklist")
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
        if len(words_in(x.get("summary", ""))) > 25:
            fails.append("summary_too_long")
        if st and f'{st["correct"]} of {st["total"]}' not in x.get("summary", ""):
            fails.append("numbers_mismatch")
        if "%" in x.get("summary", ""):
            fails.append("percentage")
    for bad in ("slow", "weak", "bad", "lazy"):
        if re.search(r"\b" + bad + r"\b", json.dumps(d).lower()):
            fails.append("judgmental_" + bad)
    return fails, d

# ---------------------------------------------------------------- test case builders
def story_case(learner, rnd):
    lv = RULES["story_levels"][str(learner["level"])]
    ints = [INTERESTS[i] for i in learner["interests"]]
    obj = rnd.choice(rnd.choice(ints)["objects"])
    plots = [p for p in CONTENT["story_plots"] if p["level"] == learner["level"]]
    plot = rnd.choice(plots)
    plot_text = plot["outline_en"].replace("{name}", learner["name"]).replace("{object}", obj)
    skill_words = [w["text"] for w in WORDS if learner["weakest"] in w["skill_ids"]]
    optional = rnd.sample(skill_words, 2)
    ex = CONTENT["story_examples"][str(learner["level"])]
    lo, hi = (4, 6) if learner["level"] == 1 else (8, 10)
    v = {
        "name": learner["name"], "object": obj, "plot": plot_text,
        "other_names": ", ".join(plot["characters"]), "level": learner["level"],
        "min_sentences": lo, "max_sentences": hi,
        "min_words": lv["min_words"], "max_words": lv["max_words"],
        "max_words_per_sentence": lv["max_words_per_sentence"], "question_types": ", ".join(lv["question_types"]),
        "optional_words": ", ".join(optional),
        "example_plot": ex["plot_en"], "example_story": ex["story_fil"],
        "_other_names_list": plot["characters"], "_optional": optional, "_plot_id": plot["id"],
        "_sent_range": (lo, hi),
    }
    return v

def words_case(learner, rnd):
    sk = learner["weakest"]
    cands = [w["text"] for w in WORDS if sk in w["skill_ids"]] or [w["text"] for w in WORDS][:20]
    return {"count": min(5, len(cands)), "skill_name_en": SKILLS[sk]["name_en"],
            "pattern_description": PATTERNS.get(sk, SKILLS[sk]["name_en"]),
            "mistake_description": RULES["mistake_types"]["P_OMIT_FINAL"]["description_en"],
            "candidate_words": ", ".join(cands), "_candidates": set(cands)}

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
    stats, lines = {}, []
    for L in LEARNERS:
        total = 10
        correct = rnd.randint(3, 9)
        mis = rnd.choice(["O_NG", "P_OMIT_FINAL", "P_SUB_VOWEL"])
        stats[L["child_id"]] = {"correct": correct, "total": total}
        lines.append(f'{L["child_id"]} | {L["name"]} | {correct} of {total} correct | skills: {L["weakest"]} | '
                     f'weakest: {L["weakest"]} | mistakes: {mis} x{rnd.randint(2, 4)} | support: guide | alert: no')
    return {"date": "2026-10-12", "present_count": len(LEARNERS), "learner_data": "\n".join(lines),
            "method_list": ", ".join(RULES["methods"].keys()), "_stats": stats}

# ---------------------------------------------------------------- mock outputs (for --mock)
def mock_output(kind, v, learner):
    if kind == "story":
        n, o = learner["name"], v["object"]
        oth = v["_other_names_list"][0]
        sents = [f"Si {n} ay may {o}.", f"Masaya si {n}.", f"Nakita ni {n} si {oth}.", f"Naglaro sila ng {o}."]
        if learner["level"] == 2:
            sents += [f"Umulan nang malakas.", f"Pumasok sila sa bahay.", f"Ngumiti si {oth}.", f"Masaya ulit si {n}."]
        qt = v["question_types"].split(", ")
        return json.dumps({"title": "Test", "paragraphs": [" ".join(sents)], "questions": [
            {"type": "who", "prompt": "Sino ang may " + o + "?", "choices": [n, "Lola", "Kuya"], "answer": n}] * 3},
            ensure_ascii=False)
    if kind == "words":
        c = sorted(v["_candidates"])[: v["count"]]
        return json.dumps({"words": [{"text": w, "syllables": [w], "meaning_en": ""} for w in c]})
    if kind == "feedback":
        return json.dumps({"message_fil": "Malapit na!", "hint_fil": "Pakinggan ulit ang salita."})
    st = v["_stats"]
    return json.dumps({"learners": [{"child_id": k, "summary": f'{s["correct"]} of {s["total"]} correct.',
                                     "next_focus_skill": "sk_ng", "next_method": "ng_sound_pairs"} for k, s in st.items()],
                       "group_note": ""})

# ---------------------------------------------------------------- main
SETTINGS_BY_KIND = {"story": (0.5, 600), "words": (0.3, 300), "feedback": (0.4, 120), "summary": (0.3, 400)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mock")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--prompt", default="all", choices=["all", "story", "words", "feedback", "summary"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--backend", default="lmstudio", choices=["lmstudio", "ollama"])
    ap.add_argument("--base-url", default=None, help="default: http://localhost:1234 (LM Studio) or :11434 (Ollama)")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--tag", default="", help="added to the output file names, for example the model name")
    a = ap.parse_args()
    if a.list_models:
        for m in list_models(a.backend, a.base_url):
            print(m)
        return
    rnd = random.Random(a.seed)
    kinds = ["story", "words", "feedback", "summary"] if a.prompt == "all" else [a.prompt]

    rows, review = [], []
    for kind in kinds:
        for i in range(a.runs):
            learner = LEARNERS[i % len(LEARNERS)]
            v = {"story": lambda: story_case(learner, rnd), "words": lambda: words_case(learner, rnd),
                 "feedback": lambda: feedback_case(learner, rnd), "summary": lambda: summary_case(rnd)}[kind]()
            prompt, unfilled = fill(TEMPLATES[kind], {k: x for k, x in v.items() if not k.startswith("_")})
            temp, num = SETTINGS_BY_KIND[kind]
            try:
                out, secs = call_model(a.model, prompt, temp, num,
                                       mock=mock_output(kind, v, learner) if a.mock else None,
                                       system=SYSTEM if kind == "story" else GENERIC_SYSTEM,
                                       backend=a.backend, base_url=a.base_url)
            except Exception as e:
                rows.append([kind, a.model, i + 1, learner["name"], "ERROR", str(e), "", ""])
                print(f"{kind} #{i+1}: ERROR {e}")
                continue
            checker = {"story": lambda: check_story(out, v, learner), "words": lambda: check_words(out, v),
                       "feedback": lambda: check_feedback(out, v), "summary": lambda: check_summary(out, v)}[kind]
            fails, parsed = checker()
            if unfilled:
                fails.append("unfilled_placeholders_" + "_".join(unfilled))
            ok = "PASS" if not fails else "FAIL"
            rows.append([kind, a.model, i + 1, learner["name"], ok, ";".join(fails), f"{secs:.1f}", out])
            print(f"{kind:8s} #{i+1:<2} {learner['name']:5s} {ok}  {secs:5.1f}s  {';'.join(fails)}")
            if kind == "story" and parsed:
                review.append((i + 1, learner, parsed, ok, fails, v["plot"]))

    tag = "_" + re.sub(r"[^A-Za-z0-9._-]+", "-", a.tag or a.model) if (a.tag or not a.mock) else ""
    res_path, rev_path = HERE / f"results{tag}.csv", HERE / f"stories_for_review{tag}.md"
    with open(res_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prompt", "model", "run", "learner", "result", "failed_checks", "seconds", "output"])
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
        secs = [float(r[6]) for r in rs if r[6]]
        avg = sum(secs) / len(secs) if secs else 0
        print(f"  {kind:8s} pass {passed}/{len(rs)}   avg {avg:.1f}s")
    print(f"Saved {res_path.name} and {rev_path.name}")

if __name__ == "__main__":
    main()
