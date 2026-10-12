# MentalPlay-Arena

Quantitative LLM role-play evaluation via psychiatric interview reenactment.

```text
data/characters.jsonl ─► PatientAgent (LLM) ─► Interviewer (scale questions)
        │                                          │
        └────────── ground truth ◄── evaluation ────┘
```

---

## Requirements

- Python 3.11+ (managed by [uv](https://docs.astral.sh/uv/))
- An OpenAI-compatible LLM endpoint (cloud or local vllm)

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Configure credentials
cp .env.example .env
#    then edit .env: LLM_API_KEY / LLM_API_BASE_URL / LLM_API_MODEL

# 3. Initialize database and import data
uv run mentalplay-arena init-db
uv run mentalplay-arena import-data
```

Done. You can now run evaluations (see below).

## Run

### CLI

```bash
# Run one character against one/many scales (scale mode = fresh patient per scale)
uv run mentalplay-arena run -c character-001 -m scale -s PHQ-9,GAD-7

# Interview mode = one shared patient across scales
uv run mentalplay-arena run -c character-001 -m interview

# Offline run with a deterministic (mock) patient — no API cost
uv run mentalplay-arena run -c character-001 -m scale -s PHQ-9 --mock

# Score a completed run against ground truth
uv run mentalplay-arena evaluate --run-id 3

# Show database contents
uv run mentalplay-arena status

# Anonymity audit (exit 0 = clean; run before packaging a paper submission)
uv run mentalplay-arena audit
```

### HTTP API

```bash
uv run mentalplay-arena serve --port 8000
# or: uv run uvicorn mentalplay_arena.api:app --port 8000
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/characters?limit=5
curl http://127.0.0.1:8000/scales

# Create + run an evaluation (returns 202, polls via GET /runs/{id})
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"character_id":"character-001","mode":"scale","scales":["PHQ-9"],"mock":true}'

curl http://127.0.0.1:8000/runs/1
curl http://127.0.0.1:8000/runs/1/results
curl -X POST http://127.0.0.1:8000/runs/1/evaluate
curl http://127.0.0.1:8000/metrics/overview
```

### Local model (vllm)

```bash
# 1. Serve a local model on :8001 (downloads once via hf-mirror)
bash scripts/serve_local.sh                  # default: Qwen2.5-0.5B-Instruct

# 2. Point the app at it
#    in .env: LLM_ACTIVE_BACKEND=local

# 3. Run
uv run mentalplay-arena run -c character-001 -m scale -s PHQ-9
```

### Translation (Chinese → English assets)

```bash
# Batch-translate the Chinese data-collection prompts into data/prompts/
uv run mentalplay-arena translate
```

### Tests

```bash
uv run pytest        # fully offline (LLM forced to mock)
```

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_ACTIVE_BACKEND` | `api` | `api` \| `local` \| `mock` |
| `LLM_API_BASE_URL` | — | Primary OpenAI-compatible endpoint |
| `LLM_API_KEY` | — | API key |
| `LLM_API_MODEL` | — | Model name |
| `LLM_BACKUP_BASE_URL/KEY/MODEL` | — | Optional backup provider |
| `LLM_LOCAL_BASE_URL` | `http://127.0.0.1:8001/v1` | vllm endpoint |
| `LLM_LOCAL_MODEL` | `Qwen2.5-0.5B-Instruct` | vllm model |
| `LLM_TIMEOUT / MAX_TOKENS / TEMPERATURE / BATCH_SIZE` | `60 / 2048 / 0.7 / 10` | LLM parameters |
| `MAX_TURNS_PER_SCALE` | `1000` | Interview length guard |
| `MEMORY_METHOD` | `none` | Patient memory: `none` \| `window` |
| `DATABASE_PATH` | `data/storage/arena.db` | SQLite location (relative) |
| `RUNS_DIR` | `data/runs` | Conversation/result output |
| `HF_ENDPOINT` | `https://hf-mirror.com` | Model download mirror |

## Project layout

```text
MentalPlay-Arena/
├── .env                    # configuration (gitignored)
├── manifest.yaml           # single scale registry (32 scales)
├── data/
│   ├── characters.jsonl    # 308 patient cases
│   ├── ground_truth/       # expert-annotated results
│   ├── scales/{Scale}/     # 21 interview modules
│   ├── prompts/            # translated prompts + templates/
│   └── storage/arena.db    # SQLite
├── scripts/                # translate.py, serve_local.sh
├── src/mentalplay_arena/   # package (config, db, llm, rules, registry,
│                           #   module_scoring, patient, interviewer,
│                           #   runner, evaluation, api, cli)
└── tests/                  # offline pytest suite
```

## Known issues

- **vllm local serving** fails on this machine because the installed
  `flash_attn` binary is incompatible with the system torch build
  (`undefined symbol: c10_cuda_check_implementation`). This is a
  machine-environment problem — reinstall a matching `flash-attn`/`torch` pair
  for the vllm environment, or serve the model via another OpenAI-compatible
  server. The `LLM_ACTIVE_BACKEND=local` path is covered by the test suite.
