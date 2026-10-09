"""Ollama chat client. Localhost only; no other network calls.

One call: POST {BASE_URL}/api/chat with stream false, keep_alive 30m, thinking off, and a JSON schema
(or "json") in the format field, as content/prompts.md section 0 asks. Any failure (Ollama not running,
timeout, bad reply) raises ModelError, which the jobs turn into the fallback. After a refused connection
(Ollama not running) calls are skipped for PAUSE_SECONDS, so queued jobs fall back at once.
"""
import json
import time
import urllib.error
import urllib.request

from backend.llm.harness import tp

BASE_URL = "http://localhost:11434"
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
        raise ModelError(f"Ollama at {BASE_URL} refused a connection less than {PAUSE_SECONDS} s ago; skipped")
    payload = {
        "model": model, "stream": False, "keep_alive": KEEP_ALIVE, "think": False,
        "format": schema or "json",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    request = urllib.request.Request(f"{BASE_URL}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
        text = data["message"]["content"]
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):      # not running (a timeout is only slow)
            _down_until = time.monotonic() + PAUSE_SECONDS
        raise ModelError(f"Ollama at {BASE_URL}: {e.reason}") from e
    except (OSError, ValueError, KeyError, TypeError) as e:  # timeouts are OSErrors too
        raise ModelError(f"Ollama at {BASE_URL}: {e}") from e
    return tp.clean_output(text), data.get("done_reason", "stop")


def available() -> bool:
    """True when Ollama answers on localhost (quick check, 2 s)."""
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/tags", timeout=2):
            return True
    except OSError:
        return False
