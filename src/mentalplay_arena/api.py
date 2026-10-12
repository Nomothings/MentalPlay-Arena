"""FastAPI backend for MentalPlay-Arena.

Exposes the full evaluation workflow over HTTP so a future frontend can drive
it: characters, scales, run creation (executed on a background thread), run
status/results, and evaluation metrics. No frontend ships with this version.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import get_settings
from .db import Database
from .evaluation import evaluate_prediction
from .llm import MockLLM, get_llm
from .prediction import shape_prediction
from .registry import Registry
from .runner import Runner

settings = get_settings()
db = Database(settings.resolve(settings.database_path))
registry = Registry(settings)

app = FastAPI(
    title="MentalPlay-Arena API",
    description="Quantitative LLM role-play evaluation via psychiatric interview reenactment.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ------------------------------------------------------------------- schemas

class RunRequest(BaseModel):
    character_id: str
    mode: str = Field("scale", pattern="^(scale|interview)$")
    scales: list[str] | None = None
    mock: bool = False


class RunResult(BaseModel):
    run_id: int
    status: str
    character_id: str
    mode: str
    backend: str
    model: str


# ------------------------------------------------------------------- helpers

def _run_background(
    run_id: int, character_id: str, mode: str, scales: list[str] | None, mock: bool = False
) -> None:
    try:
        llm = MockLLM() if mock else get_llm()
        runner = Runner(
            character_id,
            mode,
            scales=scales,
            db=db,
            registry=registry,
            llm=llm,
            verbose=False,
            run_id=run_id,
        )
        runner.run()
    except Exception as exc:  # noqa: BLE001 - report any failure on the run row
        db.update_run(run_id, status="failed", error=str(exc))


# ------------------------------------------------------------------- health

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": str(db.path), "backend": settings.llm_active_backend}


# ----------------------------------------------------------------- characters

@app.get("/characters")
def list_characters(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str = Query(""),
) -> dict:
    rows = db.list_characters(limit=limit, offset=offset, search=search)
    return {"total": len(rows), "items": [{"id": r["id"], "info": r["character_info"][:200]} for r in rows]}


@app.get("/characters/{character_id}")
def get_character(character_id: str) -> dict:
    character = db.get_character(character_id)
    if not character:
        raise HTTPException(404, f"Character {character_id} not found")
    return character


# ------------------------------------------------------------------- scales

@app.get("/scales")
def list_scales() -> dict:
    items = []
    for name in registry.all_names():
        d = registry.scale(name)
        items.append({"name": name, "format": d.format, "has_module": d.has_module,
                      "labels": d.labels if d.is_list else list(d.dimensions)})
    return {"total": len(items), "items": items}


@app.get("/scales/{scale}")
def get_scale(scale: str) -> dict:
    try:
        definition = registry.scale(scale)
    except KeyError:
        raise HTTPException(404, f"Unknown scale {scale}")
    result = {"name": scale, "format": definition.format, "labels": definition.labels}
    if definition.has_module:
        questions = registry.load_inquiries(scale)
        result["question_count"] = len(questions)
        result["sample_questions"] = [q["question_text"] for q in questions[:3]]
    return result


# --------------------------------------------------------------------- runs

@app.post("/runs", status_code=202)
def create_run(request: RunRequest) -> RunResult:
    if not db.get_character(request.character_id):
        raise HTTPException(404, f"Character {request.character_id} not found")
    run_id = db.create_run(
        character_id=request.character_id,
        mode=request.mode,
        backend="mock" if request.mock else settings.llm_active_backend,
        model="mock" if request.mock else (settings.llm_api_model or settings.llm_local_model),
    )
    thread = threading.Thread(
        target=_run_background,
        args=(run_id, request.character_id, request.mode, request.scales, request.mock),
        daemon=True,
    )
    thread.start()
    return RunResult(run_id=run_id, status="running", character_id=request.character_id,
                     mode=request.mode, backend="mock" if request.mock else settings.llm_active_backend,
                     model="mock" if request.mock else settings.llm_api_model)


@app.get("/runs")
def list_runs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict:
    rows = db.list_runs(limit=limit, offset=offset)
    return {"total": len(rows), "items": rows}


@app.get("/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    if run.get("result_json"):
        run["result"] = json.loads(run["result_json"])
    return run


@app.get("/runs/{run_id}/answers")
def get_run_answers(run_id: int) -> dict:
    if not db.get_run(run_id):
        raise HTTPException(404, f"Run {run_id} not found")
    return {"run_id": run_id, "answers": db.get_answers(run_id)}


@app.get("/runs/{run_id}/scores")
def get_run_scores(run_id: int) -> dict:
    if not db.get_run(run_id):
        raise HTTPException(404, f"Run {run_id} not found")
    return {"run_id": run_id, "scores": db.get_scores(run_id)}


@app.get("/runs/{run_id}/conversation")
def get_run_conversation(run_id: int) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    log_path = run.get("conversation_log")
    if not log_path or not Path(log_path).exists():
        return {"run_id": run_id, "messages": []}
    messages = []
    with Path(log_path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                messages.append(json.loads(line))
    return {"run_id": run_id, "messages": messages}


@app.get("/runs/{run_id}/results")
def get_run_results(run_id: int) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    result = json.loads(run["result_json"]) if run["result_json"] else {}
    shaped: dict = {"id": result.get("id")}
    for scale, value in result.items():
        if scale in {"id", "mode", "errors"} or not isinstance(value, dict):
            continue
        shaped.update(shape_prediction(scale, value, registry))
    return {"run_id": run_id, "status": run["status"], "prediction": shaped,
            "raw_result": result, "scores": db.get_scores(run_id)}


# -------------------------------------------------------------- evaluation

@app.post("/runs/{run_id}/evaluate")
def evaluate_run(run_id: int) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    result = json.loads(run["result_json"]) if run["result_json"] else {}
    gt = db.get_ground_truth(result.get("id"))
    if not gt:
        raise HTTPException(404, f"No ground truth for {result.get('id')}")
    shaped: dict = {"id": result.get("id")}
    for scale, value in result.items():
        if scale in {"id", "mode", "errors"} or not isinstance(value, dict):
            continue
        shaped.update(shape_prediction(scale, value, registry))
    scores = evaluate_prediction(shaped, gt, registry)
    for scale, value in scores.items():
        if scale in {"id", "total_score", "details"}:
            continue
        db.add_evaluation_result(run_id, scale, _metric_for(scale), value)
    return {"run_id": run_id, "scores": scores}


@app.get("/evaluations")
def list_evaluations(run_id: int | None = None) -> dict:
    if run_id is not None:
        rows = db.get_evaluation_results(run_id)
        return {"total": len(rows), "items": rows}
    # aggregate over all runs
    items = []
    for run in db.list_runs(limit=200):
        rows = db.get_evaluation_results(run["id"])
        items.extend(rows)
    return {"total": len(items), "items": items}


@app.get("/metrics/overview")
def metrics_overview() -> dict:
    """Aggregate metrics across evaluated runs."""
    aggregated: dict[str, list[float]] = {}
    for run in db.list_runs(limit=500):
        for row in db.get_evaluation_results(run["id"]):
            aggregated.setdefault(row["scale"], []).append(row["value"])
    return {
        scale: {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4) if values else 0.0,
        }
        for scale, values in aggregated.items()
    }


def _metric_for(scale: str) -> str:
    try:
        return "f1_score" if registry.scale(scale).is_list else "ordinal_similarity"
    except KeyError:
        return "f1_score"
