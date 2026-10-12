#!/usr/bin/env bash
# Serve a local model with vllm as an OpenAI-compatible API.
#
# Usage: bash scripts/serve_local.sh [model] [port]
#   model  default $LLM_LOCAL_MODEL (from .env), e.g. Qwen2.5-0.5B-Instruct
#   port   default 8001
#
# The model is downloaded on first start through HF_ENDPOINT (hf-mirror.com in
# this environment). After it is up, set LLM_ACTIVE_BACKEND=local in .env and
# run: uv run mentalplay-arena run -c character-001 -m scale -s PHQ-9

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Load .env variables (only the ones we need) without clobbering the shell.
if [ -f "$ROOT/.env" ]; then
  export HF_ENDPOINT="$(grep -E '^HF_ENDPOINT=' "$ROOT/.env" | cut -d= -f2-)"
  export LLM_LOCAL_MODEL="$(grep -E '^LLM_LOCAL_MODEL=' "$ROOT/.env" | cut -d= -f2-)"
fi

MODEL="${1:-${LLM_LOCAL_MODEL:-Qwen2.5-0.5B-Instruct}}"
PORT="${2:-8001}"

# Prefer a locally downloaded copy under data/models/ so no hub access is needed.
LOCAL_DIR="$ROOT/data/models/$MODEL"
if [ -d "$LOCAL_DIR" ]; then
  MODEL_REF="$LOCAL_DIR"
  echo "Serving local copy at $MODEL_REF"
else
  MODEL_REF="$MODEL"
  echo "Serving hub model '$MODEL_REF' (HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com})"
fi

vllm serve "$MODEL_REF" \
  --port "$PORT" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.2

echo "Local model ready at http://127.0.0.1:${PORT}/v1"
