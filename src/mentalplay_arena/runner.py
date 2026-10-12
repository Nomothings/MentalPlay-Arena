"""Run orchestration.

Runner drives a full evaluation run for one character in one mode:
  - scale     : a fresh PatientAgent (NoMemory) + Interviewer per scale
  - interview : one shared PatientAgent (WindowMemory) across all scales

Conversation is streamed to data/runs/{run_id}/conversation.jsonl; results and
scores are persisted incrementally after each scale so a mid-run failure never
loses completed scales.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Settings, get_settings
from .db import Database
from .interviewer import Interviewer
from .llm import get_llm
from .memory import create_memory
from .module_scoring import compute_ksads_scores, compute_scale_scores
from .patient import PatientAgent
from .registry import Registry

SCALE_MODE = "scale"
INTERVIEW_MODE = "interview"


class Runner:
    def __init__(
        self,
        character_id: str,
        mode: str,
        scales: list[str] | None = None,
        db: Database | None = None,
        registry: Registry | None = None,
        settings: Settings | None = None,
        llm=None,
        verbose: bool = True,
        run_id: int | None = None,
    ):
        self.settings = settings or get_settings()
        self.character_id = character_id
        self.mode = mode
        self.verbose = verbose
        self.llm = llm if llm is not None else get_llm(self.settings)
        self.registry = registry or Registry(self.settings)
        self.db = db or Database(self.settings.resolve(self.settings.database_path))
        self.scales = scales or self.registry.evaluation_scope

        self.run_id: int | None = run_id
        self.backend = self.settings.llm_active_backend
        self.model = self._model_name()
        self.result: dict = {"id": character_id, "mode": mode}
        self.conversation_file: Path | None = None
        self._conversation_handle = None

    def _model_name(self) -> str:
        if self.backend == "local":
            return self.settings.llm_local_model
        if self.backend == "api":
            return self.settings.llm_api_model
        return "mock"

    # ------------------------------------------------------------- lifecycle

    def _setup(self) -> None:
        self.db.init_schema()
        character = self.db.get_character(self.character_id)
        if not character:
            raise ValueError(f"Character not found: {self.character_id}")

        runs_dir = self.settings.resolve(self.settings.runs_dir)
        if self.run_id is None:
            self.run_id = self.db.create_run(
                character_id=self.character_id,
                mode=self.mode,
                backend=self.backend,
                model=self.model,
            )
        else:
            self.db.update_run(self.run_id, status="running", error=None)
        run_dir = runs_dir / str(self.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_file = run_dir / "conversation.jsonl"
        self._conversation_handle = self.conversation_file.open("w", encoding="utf-8")
        self.db.update_run(self.run_id, conversation_log=str(self.conversation_file))

    def _close(self) -> None:
        if self._conversation_handle:
            self._conversation_handle.close()
            self._conversation_handle = None

    def _log_message(self, role: str, content: str, scale: str) -> None:
        if not self._conversation_handle:
            return
        record = {"role": role, "content": content, "scale": scale}
        self._conversation_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._conversation_handle.flush()

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    # ------------------------------------------------------------------ run

    def run(self) -> dict:
        self._setup()
        errors: list[str] = []

        if self.mode == INTERVIEW_MODE:
            self._run_interview(errors)
        else:
            self._run_scale(errors)

        status = "completed" if not errors else "partial"
        if errors:
            self.result["errors"] = errors

        self.db.update_run(
            self.run_id,
            status=status,
            result_json=json.dumps(self.result, ensure_ascii=False),
        )
        self._close()
        return self.result

    def _new_patient(self, shared: PatientAgent | None) -> tuple[PatientAgent, bool]:
        """Create a fresh patient (scale mode) or reuse the shared one."""
        if shared is not None:
            return shared, False
        character = self.db.get_character(self.character_id)
        memory = create_memory("none", self.settings.memory_window_size)
        return PatientAgent(self.character_id, character["character_info"], llm=self.llm, memory=memory, settings=self.settings), True

    def _run_interview(self, errors: list[str]) -> None:
        character = self.db.get_character(self.character_id)
        shared = PatientAgent(
            self.character_id,
            character["character_info"],
            llm=self.llm,
            memory=create_memory("window", self.settings.memory_window_size),
            settings=self.settings,
        )
        for scale in self.scales:
            try:
                prediction = self._run_single_scale(scale, shared)
                self.result[scale] = prediction
                self._persist_scale(scale)
            except Exception as exc:  # noqa: BLE001 - per-scale isolation
                errors.append(f"{scale}: {exc}")
                self._log(f"  [ERROR] {scale}: {exc}")

    def _run_scale(self, errors: list[str]) -> None:
        for scale in self.scales:
            try:
                prediction = self._run_single_scale(scale, None)
                self.result[scale] = prediction
                self._persist_scale(scale)
            except Exception as exc:  # noqa: BLE001 - per-scale isolation
                errors.append(f"{scale}: {exc}")
                self._log(f"  [ERROR] {scale}: {exc}")

    def _run_single_scale(self, scale: str, shared_patient: PatientAgent | None) -> dict:
        self._log(f"=== {scale} ({self.mode}) ===")
        patient, is_new = self._new_patient(shared_patient)
        interviewer = Interviewer(scale, llm=self.llm, registry=self.registry, settings=self.settings)

        question = interviewer.start()
        self._log_message("assistant", question["question_text"], scale)
        self._log(f"  Q: {question['question_text']}")

        while True:
            if is_new and patient.memory:
                pass  # patient already holds its character; nothing to reset
            answer = patient.chat(question["question_text"])
            self._log_message("user", answer, scale)
            self._log(f"  A: {answer[:80]}")

            outcome = interviewer.submit_answer(question["question_id"], answer)
            if outcome["status"] == "finished":
                break
            if outcome["status"] == "error":
                interviewer.error = outcome.get("message", "error")
                break
            question = outcome["question"]
            self._log_message("assistant", question["question_text"], scale)
            self._log(f"  Q: {question['question_text'][:80]}")

        prediction = self._score_scale(scale, interviewer)
        self._log(f"  => {scale}: {prediction}")
        return prediction

    def _score_scale(self, scale: str, interviewer: Interviewer) -> dict:
        answers = interviewer.get_answers()
        # Persist per-question answers to the database.
        for t in interviewer.turns:
            self.db.add_answer(
                run_id=self.run_id,
                scale=scale,
                question_id=t.question_id,
                question_text=t.question_text,
                mapped_answer=t.mapped_answer,
                raw_answer=t.raw_answer,
                category_id=t.category_id,
            )

        if scale == "K-SADS":
            result = compute_ksads_scores(interviewer.get_category_scores(), self.registry, self.settings)
        else:
            result = compute_scale_scores(scale, answers, self.registry, self.settings)

        self.db.add_score(
            run_id=self.run_id,
            scale=scale,
            total_score=result.total,
            severity=result.severity,
            dimensions=result.dimensions,
        )
        return {
            "scale": scale,
            "total_score": result.total,
            "severity": result.severity,
            "dimensions": result.dimensions,
            "answers": answers,
        }

    def _persist_scale(self, scale: str) -> None:
        """Incremental save: rewrite the run's result_json after each scale."""
        self.db.update_run(self.run_id, result_json=json.dumps(self.result, ensure_ascii=False))
