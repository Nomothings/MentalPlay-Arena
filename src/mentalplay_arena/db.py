"""SQLite persistence layer for MentalPlay-Arena.

Single database (data/storage/arena.db) holding characters, ground truth,
runs, answers, scores and evaluation results. Scale module definitions stay
as files under data/scales/ (loaded at runtime by registry.py).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    character_info TEXT NOT NULL,
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ground_truth (
    id TEXT PRIMARY KEY REFERENCES characters(id),
    payload TEXT NOT NULL,
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL REFERENCES characters(id),
    mode TEXT NOT NULL CHECK (mode IN ('scale', 'interview')),
    scale TEXT,
    backend TEXT,
    model TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'partial', 'failed')),
    conversation_log TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scale TEXT NOT NULL,
    category_id INTEGER,
    question_id TEXT NOT NULL,
    question_text TEXT,
    mapped_answer TEXT,
    raw_answer TEXT,
    score TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scale TEXT NOT NULL,
    total_score REAL,
    severity TEXT,
    dimensions TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    scale TEXT NOT NULL,
    metric TEXT NOT NULL CHECK (metric IN ('f1_score', 'ordinal_similarity')),
    value REAL NOT NULL,
    detail TEXT,
    evaluated_at TEXT DEFAULT (datetime('now'))
);
"""


class Database:
    """Thin wrapper around a SQLite connection with row helpers."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.session() as conn:
            conn.executescript(SCHEMA)

    # ---------------------------------------------------------------- import

    def upsert_character(self, character_id: str, character_info: str) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO characters (id, character_info) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET character_info = excluded.character_info",
                (character_id, character_info),
            )

    def upsert_ground_truth(self, character_id: str, payload: dict) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO ground_truth (id, payload) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (character_id, json.dumps(payload, ensure_ascii=False)),
            )

    def count_characters(self) -> int:
        with self.session() as conn:
            return conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]

    def count_ground_truth(self) -> int:
        with self.session() as conn:
            return conn.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0]

    # ---------------------------------------------------------------- reads

    def get_character(self, character_id: str) -> dict | None:
        with self.session() as conn:
            row = conn.execute(
                "SELECT id, character_info FROM characters WHERE id = ?", (character_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_characters(self, limit: int = 100, offset: int = 0, search: str = "") -> list[dict]:
        sql = "SELECT id, character_info FROM characters"
        params: list[Any] = []
        if search:
            sql += " WHERE id LIKE ?"
            params.append(f"%{search}%")
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self.session() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_ground_truth(self, character_id: str) -> dict | None:
        with self.session() as conn:
            row = conn.execute(
                "SELECT payload FROM ground_truth WHERE id = ?", (character_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    # ---------------------------------------------------------------- runs

    def create_run(
        self,
        character_id: str,
        mode: str,
        scale: str | None = None,
        backend: str = "",
        model: str = "",
        conversation_log: str = "",
    ) -> int:
        with self.session() as conn:
            cur = conn.execute(
                "INSERT INTO runs (character_id, mode, scale, backend, model, conversation_log) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (character_id, mode, scale, backend, model, conversation_log),
            )
            return int(cur.lastrowid)

    def update_run(self, run_id: int, **fields: Any) -> None:
        allowed = {
            "status", "result_json", "error", "conversation_log", "completed_at",
        }
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        cols = ", ".join(f"{k} = ?" for k in sets)
        with self.session() as conn:
            conn.execute(f"UPDATE runs SET {cols} WHERE id = ?", (*sets.values(), run_id))

    def get_run(self, run_id: int) -> dict | None:
        with self.session() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- answers

    def add_answer(
        self,
        run_id: int,
        scale: str,
        question_id: str,
        mapped_answer: str,
        raw_answer: str,
        question_text: str = "",
        category_id: int | None = None,
        score: str | None = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO answers (run_id, scale, category_id, question_id, question_text, "
                "mapped_answer, raw_answer, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, scale, category_id, question_id, question_text, mapped_answer,
                 raw_answer, score),
            )

    def get_answers(self, run_id: int) -> list[dict]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM answers WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- scores

    def add_score(
        self,
        run_id: int,
        scale: str,
        total_score: float | None,
        severity: str,
        dimensions: dict | None = None,
    ) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO scores (run_id, scale, total_score, severity, dimensions) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, scale, total_score, severity,
                 json.dumps(dimensions, ensure_ascii=False) if dimensions else None),
            )

    def get_scores(self, run_id: int) -> list[dict]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM scores WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("dimensions"):
                d["dimensions"] = json.loads(d["dimensions"])
            out.append(d)
        return out

    # ---------------------------------------------------------------- evaluation

    def add_evaluation_result(
        self, run_id: int, scale: str, metric: str, value: float, detail: dict | None = None
    ) -> None:
        with self.session() as conn:
            conn.execute(
                "INSERT INTO evaluation_results (run_id, scale, metric, value, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, scale, metric, value,
                 json.dumps(detail, ensure_ascii=False) if detail else None),
            )

    def get_evaluation_results(self, run_id: int) -> list[dict]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluation_results WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("detail"):
                d["detail"] = json.loads(d["detail"])
            out.append(d)
        return out
