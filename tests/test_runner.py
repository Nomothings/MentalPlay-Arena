"""Tests for the run orchestration (runner.py) with a mock LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentalplay_arena.config import get_settings
from mentalplay_arena.llm import MockLLM
from mentalplay_arena.registry import Registry
from mentalplay_arena.runner import INTERVIEW_MODE, SCALE_MODE, Runner


@pytest.fixture(scope="module")
def registry():
    return Registry(get_settings())


@pytest.fixture
def seeded_db(fresh_db):
    fresh_db.upsert_character("character-001", "Female patient, 19, obsessive-compulsive symptoms for a year.")
    fresh_db.upsert_ground_truth("character-001", {"id": "character-001", "K-SADS": ["Obsessive-compulsive disorder"]})
    return fresh_db


class TestRunnerScaleMode:
    def test_runs_two_scales_and_persists(self, seeded_db, registry, mock_llm, tmp_path):
        runner = Runner(
            "character-001",
            SCALE_MODE,
            scales=["PHQ-9", "GAD-7"],
            db=seeded_db,
            registry=registry,
            settings=get_settings(),
            llm=mock_llm,
            verbose=False,
        )
        result = runner.run()

        assert result["id"] == "character-001"
        assert result["mode"] == "scale"
        assert "PHQ-9" in result and "GAD-7" in result
        assert result["PHQ-9"]["total_score"] is not None

        # run row updated with completed status + result
        run = seeded_db.get_run(runner.run_id)
        assert run["status"] == "completed"
        assert run["result_json"] is not None

        # answers + scores persisted
        answers = seeded_db.get_answers(runner.run_id)
        assert answers, "answers should be persisted"
        scores = seeded_db.get_scores(runner.run_id)
        assert len(scores) == 2

        # conversation JSONL written
        log_path = Path(run["conversation_log"])
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) > 2

    def test_failed_scale_isolated(self, seeded_db, registry, mock_llm, tmp_path):
        runner = Runner(
            "character-001",
            SCALE_MODE,
            scales=["PHQ-9", "NOPE-NOT-A-SCALE"],
            db=seeded_db,
            registry=registry,
            settings=get_settings(),
            llm=mock_llm,
            verbose=False,
        )
        result = runner.run()
        # valid scale scored, unknown scale isolated as an error
        assert "PHQ-9" in result
        assert result.get("errors")
        run = seeded_db.get_run(runner.run_id)
        assert run["status"] in {"partial", "failed"}


class TestRunnerInterviewMode:
    def test_shared_patient_and_results(self, seeded_db, registry, mock_llm, tmp_path):
        runner = Runner(
            "character-001",
            INTERVIEW_MODE,
            scales=["PHQ-9", "GAD-7"],
            db=seeded_db,
            registry=registry,
            settings=get_settings(),
            llm=mock_llm,
            verbose=False,
        )
        result = runner.run()
        assert "PHQ-9" in result and "GAD-7" in result
        run = seeded_db.get_run(runner.run_id)
        assert run["mode"] == "interview"
        assert run["status"] == "completed"
