"""Compare local Ollama models on one simple Tagalog sentence with JSON output.

Usage: python scripts/test_ollama.py
"""
import json
import time
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELS = ["llama3.2:3b", "qwen2.5:3b", "phi3:mini"]
PROMPT = (
    "Write one simple Tagalog sentence for a child learning to read. "
    'Reply only with JSON in this form: {"sentence": "..."}'
)


def ask(model: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "format": "json",
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["message"]["content"]


def main():
    for model in MODELS:
        start = time.perf_counter()
        try:
            answer = ask(model)
        except Exception as e:
            answer = f"ERROR: {e}"
        seconds = time.perf_counter() - start
        print(f"{model:<12} {seconds:6.2f}s  {answer}")


if __name__ == "__main__":
    main()
