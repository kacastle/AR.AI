"""Model client: the local model (Ollama or LM Studio, localhost) and, only when LLM_PROVIDER says so, Gemini.

One call: POST {BASE_URL}/api/chat with stream false, keep_alive 30m, thinking off, and a JSON schema
(or "json") in the format field, as content/prompts.md section 0 asks. Any failure (Ollama not running,
timeout, bad reply) raises ModelError, which the jobs turn into the fallback. After a refused connection
(Ollama not running) calls are skipped for PAUSE_SECONDS, so queued jobs fall back at once.

LLM_BACKEND=lmstudio uses LM Studio's local server instead (OpenAI-style POST /v1/chat/completions on
localhost:1234, the JSON schema as response_format, reasoning_effort none so Gemma 4 does not think).
"""
import json
import os
import time
import urllib.error
import urllib.request

from backend.llm.harness import tp

LMSTUDIO = os.environ.get("LLM_BACKEND") == "lmstudio"
BASE_URL = "http://localhost:1234" if LMSTUDIO else "http://localhost:11434"
NAME = "LM Studio" if LMSTUDIO else "Ollama"
KEEP_ALIVE = "30m"          # the model stays loaded during a session
TIMEOUT_SECONDS = 300       # a story takes about a minute on the demo laptop
PAUSE_SECONDS = 30          # after Ollama refused a connection
_down_until = 0.0


class ModelError(Exception):
    pass


def chat(model: str, system: str, user: str, temperature: float, num_predict: int,
         schema: dict | None = None) -> tuple[str, str]:
    """Returns (text, done_reason). The text is cleaned (no code fences or thinking blocks)."""
    global _down_until
    if time.monotonic() < _down_until:
        raise ModelError(f"{NAME} at {BASE_URL} refused a connection less than {PAUSE_SECONDS} s ago; skipped")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if LMSTUDIO:
        path, payload = "/v1/chat/completions", {
            "model": model, "stream": False, "messages": messages, "temperature": temperature,
            "max_tokens": num_predict, "reasoning_effort": "none",
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "output", "schema": schema or {"type": "object"}}},
        }
    else:
        path, payload = "/api/chat", {
            "model": model, "stream": False, "keep_alive": KEEP_ALIVE, "think": False,
            "format": schema or "json", "messages": messages,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
    request = urllib.request.Request(f"{BASE_URL}{path}", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
        if LMSTUDIO:
            choice = data["choices"][0]
            text, done = choice["message"]["content"] or "", choice.get("finish_reason", "stop")
        else:
            text, done = data["message"]["content"], data.get("done_reason", "stop")
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):      # not running (a timeout is only slow)
            _down_until = time.monotonic() + PAUSE_SECONDS
        raise ModelError(f"{NAME} at {BASE_URL}: {e.reason}") from e
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:  # timeouts are OSErrors too
        raise ModelError(f"{NAME} at {BASE_URL}: {e}") from e
    return tp.clean_output(text), done


def warm(model: str) -> None:
    """Load the model into memory now (Ollama's load call: /api/generate without a prompt), so the
    first real call does not pay for loading. keep_alive keeps it loaded."""
    global _down_until
    if LMSTUDIO:            # LM Studio loads the model on the first call; check it answers
        if not available():
            raise ModelError(f"{NAME} at {BASE_URL} is not running")
        return
    request = urllib.request.Request(f"{BASE_URL}/api/generate",
                                     data=json.dumps({"model": model, "keep_alive": KEEP_ALIVE}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            response.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            _down_until = time.monotonic() + PAUSE_SECONDS
        raise ModelError(f"Ollama at {BASE_URL}: {e.reason}") from e
    except OSError as e:
        raise ModelError(f"Ollama at {BASE_URL}: {e}") from e


def available() -> bool:
    """True when the model server answers on localhost (quick check, 2 s)."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}{'/v1/models' if LMSTUDIO else '/api/tags'}", timeout=2):
            return True
    except OSError:
        return False


# ---------- optional cloud model (Gemini), local first ----------
# LLM_PROVIDER=local (default): every job runs on the local model above; nothing leaves the laptop.
# LLM_PROVIDER=auto: personal story jobs go to Gemini when the laptop is online and GEMINI_API_KEY is set;
#   everything else stays local, and any cloud error falls back to the local model.
# LLM_PROVIDER=cloud: as auto, for every job kind.
# The learner's name never leaves the laptop: it is replaced by a placeholder before the call and put back after.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLOUD_KINDS = {"story"}
ONLINE_CACHE_SECONDS = 60
_online = (0.0, False)


def provider() -> str:
    return os.environ.get("LLM_PROVIDER", "local").lower()


def online() -> bool:
    """True when the cloud API answers (2 s check, cached for a minute). Any HTTP reply counts as online."""
    global _online
    checked, ok = _online
    if time.monotonic() - checked < ONLINE_CACHE_SECONDS:
        return ok
    try:
        with urllib.request.urlopen("https://generativelanguage.googleapis.com/", timeout=2):
            ok = True
    except urllib.error.HTTPError:
        ok = True
    except OSError:
        ok = False
    _online = (time.monotonic(), ok)
    return ok


def use_cloud(kind: str) -> bool:
    mode = provider()
    if mode not in ("auto", "cloud") or not os.environ.get("GEMINI_API_KEY"):
        return False
    return (mode == "cloud" or kind in CLOUD_KINDS) and online()


def gemini_chat(system: str, user: str, temperature: float, num_predict: int) -> tuple[str, str]:
    """One Gemini call (JSON output, no thinking). Returns (text, done_reason) like chat()."""
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max(num_predict * 2, 1024),
                             "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}},
    }
    request = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "x-goog-api-key": os.environ.get("GEMINI_API_KEY", "")})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read())
        candidate = data["candidates"][0]
        text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
        done = "length" if candidate.get("finishReason") == "MAX_TOKENS" else "stop"
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
        raise ModelError(f"Gemini: {e}") from e
    return tp.clean_output(text), done


def _hide(text: str, names: list[str]) -> str:
    for k, name in enumerate(names, 1):
        text = text.replace(name, f"NAME_{k}")
    return text


def _unhide(text: str, names: list[str]) -> str:
    for k, name in enumerate(names, 1):
        text = text.replace(f"NAME_{k}", name)
    return text


def generate(kind: str, model: str, system: str, user: str, temperature: float, num_predict: int,
             schema: dict | None = None, names=()) -> tuple[str, str, str]:
    """(text, done_reason, provider): the cloud model when use_cloud(kind), else (or after a cloud error) the
    local model. names: the learner names to keep on the laptop."""
    names = sorted({n for n in names if n}, key=len, reverse=True)
    if use_cloud(kind):
        try:
            text, done = gemini_chat(_hide(system, names), _hide(user, names), temperature, num_predict)
            return _unhide(text, names), done, "cloud"
        except ModelError:
            pass                                   # offline after all, quota, bad reply: stay local
    text, done = chat(model, system, user, temperature, num_predict, schema=schema)
    return text, done, "local"
