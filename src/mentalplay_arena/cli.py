"""Command-line interface for MentalPlay-Arena (typer)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import get_settings
from .db import Database

app = typer.Typer(help="MentalPlay-Arena: LLM role-play evaluation via psychiatric interview reenactment.")


def _db() -> Database:
    settings = get_settings()
    return Database(settings.resolve(settings.database_path))


@app.command()
def init_db() -> None:
    """Create the SQLite schema (idempotent)."""
    database = _db()
    database.init_schema()
    typer.echo(f"Schema ready at {database.path}")


@app.command()
def import_data() -> None:
    """Import characters.jsonl and ground truth into the database (upsert)."""
    settings = get_settings()
    database = _db()
    database.init_schema()

    characters_path = settings.resolve(settings.characters_path)
    with characters_path.open(encoding="utf-8") as f:
        n_chars = 0
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            database.upsert_character(record["id"], record["character_info"])
            n_chars += 1

    gt_path = settings.resolve(settings.ground_truth_path)
    n_gt = 0
    with gt_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            database.upsert_ground_truth(record["id"], record)
            n_gt += 1

    typer.echo(f"Imported {n_chars} characters, {n_gt} ground-truth records.")
    typer.echo(f"DB totals: {database.count_characters()} characters, {database.count_ground_truth()} ground-truth.")


@app.command()
def status() -> None:
    """Show database status."""
    database = _db()
    typer.echo(f"DB: {database.path}")
    typer.echo(f"  characters:   {database.count_characters()}")
    typer.echo(f"  ground truth: {database.count_ground_truth()}")


@app.command()
def run(
    character: str = typer.Option(..., "--character", "-c", help="Character id, e.g. character-001"),
    mode: str = typer.Option("scale", "--mode", "-m", help="scale | interview"),
    scales: str = typer.Option("", "--scales", "-s", help="Comma-separated scales (default: all evaluation scope)"),
    mock: bool = typer.Option(False, "--mock", help="Force mock LLM backend (offline)"),
) -> None:
    """Run an evaluation for one character (mock or live per .env / --mock)."""
    import json

    from .llm import get_llm
    from .registry import Registry
    from .runner import Runner

    if mock:
        from .llm import MockLLM

        llm = MockLLM()
    else:
        llm = get_llm()

    registry = Registry(get_settings())
    scale_list = [s.strip() for s in scales.split(",") if s.strip()] if scales else None

    runner = Runner(character, mode, scales=scale_list, registry=registry, llm=llm)
    result = runner.run()
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    typer.echo(f"\nRun id: {runner.run_id}  status: {result.get('errors', 'completed')}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
) -> None:
    """Start the FastAPI backend server."""
    import uvicorn

    uvicorn.run("mentalplay_arena.api:app", host=host, port=port)


@app.command()
def audit() -> None:
    """Run the anonymity audit (exit 0 = clean, for paper submissions)."""
    import subprocess
    import sys

    script = typer.get_app_dir("mentalplay-arena")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "scripts" / "audit_identity.py")],
    )
    raise typer.Exit(result.returncode)


@app.command()
def evaluate(
    run_id: int = typer.Option(..., "--run-id", help="Run id to evaluate"),
) -> None:
    """Compute metrics for a completed run against ground truth."""
    import json

    from .evaluation import evaluate_prediction
    from .prediction import shape_prediction
    from .registry import Registry

    registry = Registry(get_settings())
    db = _db()
    run = db.get_run(run_id)
    if not run:
        typer.echo(f"Run {run_id} not found.", err=True)
        raise typer.Exit(1)
    result = json.loads(run["result_json"]) if run["result_json"] else {}
    gt = db.get_ground_truth(result.get("id"))

    shaped: dict = {"id": result.get("id")}
    for scale, value in result.items():
        if scale in {"id", "mode", "errors"} or not isinstance(value, dict):
            continue
        shaped.update(shape_prediction(scale, value, registry))

    if not gt:
        typer.echo(f"No ground truth for {result.get('id')}.", err=True)
        raise typer.Exit(1)

    scores = evaluate_prediction(shaped, gt, registry)
    for scale, value in scores.items():
        if scale in {"id", "total_score"}:
            continue
        typer.echo(f"  {scale}: {value}")
    if "total_score" in scores:
        typer.echo(f"  TOTAL: {scores['total_score']}")
    typer.echo(json.dumps(scores, ensure_ascii=False, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
