#!/usr/bin/env bash
# Pull Ollama models for the model comparison, skipping any that are already local.
#
# Usage (Git Bash, from the repo root):
#   bash scripts/pull_models.sh                 # default candidates below
#   bash scripts/pull_models.sh qwen3.5:2b      # any tags you name
set -euo pipefail

MODELS=("$@")
if [ ${#MODELS[@]} -eq 0 ]; then
    MODELS=("gemma4:e4b" "qwen3.5:4b")
fi

if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama not found on PATH. Install Ollama and open a new terminal." >&2
    exit 1
fi

# First column of `ollama list` is the model tag; skip the header row.
LOCAL=$(ollama list | awk 'NR > 1 {print $1}')

for model in "${MODELS[@]}"; do
    if grep -qxF "$model" <<< "$LOCAL"; then
        echo "already local: $model"
    else
        echo "pulling: $model"
        ollama pull "$model"
    fi
done

echo
ollama list
