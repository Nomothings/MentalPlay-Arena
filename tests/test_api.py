"""End-to-end API tests using FastAPI TestClient with a mock backend.

Because the runner uses get_llm() (which reads LLM_ACTIVE_BACKEND=mock under
the offline_env fixture), POST /runs executes a mock interview without touching
any real API.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from mentalplay_arena.config import get_settings
from mentalplay_arena.db import Database
from mentalplay_arena.registry import Registry


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Seed a database with one character + ground truth, then point api.db at it.
    from mentalplay_arena import api

    db_path = tmp_path / "api_test.db"
    db = Database(db_path)
    db.init_schema()
    db.upsert_character("character-001", "Female patient, 19, obsessive-compulsive symptoms.")
    db.upsert_ground_truth("character-001", {"id": "character-001", "K-SADS": ["Obsessive-compulsive disorder"]})

    monkeypatch.setattr(api, "db", db)
    # The API module built its Database/Registry at import time from env settings;
    # rebuild them against the seeded temp DB.
    from fastapi.testclient import TestClient as TC

    client = TC(api.app)
    return client, db


class TestHealthAndReads:
    def test_health(self, client):
        client, _ = client
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_characters(self, client):
        client, _ = client
        response = client.get("/characters")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert body["items"][0]["id"] == "character-001"

    def test_scales_include_module_scales(self, client):
        client, _ = client
        response = client.get("/scales")
        body = response.json()
        names = {item["name"] for item in body["items"]}
        assert "PHQ-9" in names and "K-SADS" in names

    def test_scale_detail(self, client):
        client, _ = client
        response = client.get("/scales/PHQ-9")
        assert response.status_code == 200
        assert response.json()["question_count"] == 9


class TestRunLifecycle:
    def test_create_run_and_poll(self, client):
        client, _ = client
        response = client.post("/runs", json={"character_id": "character-001", "mode": "scale", "scales": ["PHQ-9"], "mock": True})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        # poll until completed (mock is fast)
        for _ in range(50):
            run = client.get(f"/runs/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.05)
        assert run["status"] == "completed", run

    def test_run_answers_and_conversation(self, client):
        client, _ = client
        run_id = client.post("/runs", json={"character_id": "character-001", "mode": "scale", "scales": ["PHQ-9"], "mock": True}).json()["run_id"]
        for _ in range(50):
            run = client.get(f"/runs/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.05)
        answers = client.get(f"/runs/{run_id}/answers").json()
        assert len(answers["answers"]) == 9  # PHQ-9 has 9 questions
        conv = client.get(f"/runs/{run_id}/conversation").json()
        assert len(conv["messages"]) >= 2

    def test_run_evaluate(self, client):
        client, _ = client
        run_id = client.post("/runs", json={"character_id": "character-001", "mode": "scale", "scales": ["K-SADS"], "mock": True}).json()["run_id"]
        for _ in range(200):
            run = client.get(f"/runs/{run_id}").json()
            if run["status"] != "running":
                break
            time.sleep(0.05)
        response = client.post(f"/runs/{run_id}/evaluate")
        assert response.status_code == 200
        scores = response.json()["scores"]
        assert "K-SADS" in scores

    def test_metrics_overview(self, client):
        client, _ = client
        response = client.get("/metrics/overview")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_missing_run_404(self, client):
        client, _ = client
        assert client.get("/runs/99999").status_code == 404
