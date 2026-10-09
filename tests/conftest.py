import os

# Tests never start the background model worker (it would call Ollama). Jobs still queue up,
# and tests run them with backend.llm.worker.worker.run_pending().
os.environ.setdefault("LLM_WORKER", "0")
