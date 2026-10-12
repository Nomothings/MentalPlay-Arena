"""Shared test fixtures.

All tests run offline: the LLM backend is forced to mock and storage paths
are redirected into a temporary directory, so `pytest` never touches the real
database or calls any external API.
"""

from __future__ import annotations

import pytest

from mentalplay_arena.config import reset_settings_cache


@pytest.fixture(autouse=True)
def offline_env(tmp_path, monkeypatch):
    """Force mock backend + temp storage for every test."""
    monkeypatch.setenv("LLM_ACTIVE_BACKEND", "mock")
    monkeypatch.setenv("LLM_REFINE_QUESTIONS", "false")
    monkeypatch.setenv("LLM_EMPATHIC_RESPONSES", "false")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "arena_test.db"))
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("PREDICTIONS_DIR", str(tmp_path / "predictions"))
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def mock_llm():
    from mentalplay_arena.llm import MockLLM

    return MockLLM()


@pytest.fixture
def fresh_db(tmp_path):
    from mentalplay_arena.db import Database

    db = Database(tmp_path / "fresh.db")
    db.init_schema()
    return db
